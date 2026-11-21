"""Verify installed Iris preprocessing and draw-buffer parsing without starting a game."""
import argparse
from itertools import product
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from compile_glsl import ROOT, SHADERS, configure, expand
from validate import FEATURE, WRITERS

JAVA = r'''import java.io.*;
import java.nio.file.*;
import java.util.*;
import net.irisshaders.iris.helpers.StringPair;
import net.irisshaders.iris.shaderpack.preprocessor.*;
import net.irisshaders.iris.shaderpack.parsing.*;
class WaterDirectives {
    public static void main(String[] args) throws Exception {
        Path root = Path.of(args[0]);
        String properties = Files.readString(Path.of(args[1]));
        int programs = 0, settings = 0;
        for (String line : Files.readAllLines(root.resolve("cases.tsv"))) {
            String[] c = line.split("\t");
            if (c[0].equals("shader")) {
                String source = JcppProcessor.glslPreprocessSource(Files.readString(root.resolve(c[1])), List.of());
                String route = CommentDirectiveParser.findDirective(source, CommentDirective.Type.RENDERTARGETS)
                    .map(CommentDirective::getDirective).orElse("-").strip();
                if (!route.equals(c[2])) throw new AssertionError(c[1] + " routes to " + route);
                var formats = new TreeMap<String,String>();
                for (var v : ConstDirectiveParser.findDirectives(source)) {
                    if (v.getKey().matches("colortex(7|8|9|10)Format")) formats.put(v.getKey(),v.getValue());
                }
                if (!String.join(",", formats.values()).equals(c[3].replace("-","")))
                    throw new AssertionError(c[1] + " formats " + formats);
                programs++;
                continue;
            }
            var env = new ArrayList<StringPair>();
            for (int i=4; i<c.length; i++) {
                String[] pair = c[i].split("=",2);
                env.add(new StringPair(pair[0],pair[1]));
            }
            var loaded = new Properties();
            loaded.load(new StringReader(PropertiesPreprocessor.preprocessSource(properties, env)));
            boolean active = c[1].equals("1");
            if (!loaded.getProperty("program.composite.enabled","true").equals(Boolean.toString(active)))
                throw new AssertionError("Water pass enable: "+line);
            boolean bounds=c[3].equals("1");
            if (!loaded.getProperty("program.deferred1.enabled","true").equals(Boolean.toString(bounds))
                || !Objects.equals(loaded.getProperty("size.buffer.colortex10"),bounds ? "0.125 0.125" : null))
                throw new AssertionError("Reflection bound dispatch: "+line);
            int count=0;
            for (String key : loaded.stringPropertyNames()) {
                if (!key.endsWith(".colortex8")) continue;
                boolean opaque = Set.of("gbuffers_terrain","gbuffers_entities","gbuffers_block")
                                    .contains(key.split("\\.")[1]);
                if (!loaded.getProperty(key).equals(opaque ? "off" : "ONE ONE ONE ONE"))
                    throw new AssertionError(key);
                count++;
            }
            if (count != (active ? 16 : 0)
                || loaded.containsKey("blend.gbuffers_water.colortex7") != c[2].equals("1"))
                throw new AssertionError("Water ownership settings: "+line);
            settings++;
        }
        System.out.printf("PASS: installed Iris parsed %d fragment configurations and %d setting selections%n",
                          programs,settings);
    }
}
'''


def verify(work, iris_jar, slf4j_jar):
    java=work/'WaterDirectives.java'
    java.write_text(JAVA,encoding='utf-8')
    with ZipFile(iris_jar) as iris:
        jcpp, = [n for n in iris.namelist() if n.startswith('META-INF/jars/jcpp-') and n.endswith('.jar')]
        (work/'jcpp.jar').write_bytes(iris.read(jcpp))
    cp=os.pathsep.join(map(str,(work,iris_jar.resolve(),work/'jcpp.jar',slf4j_jar.resolve())))
    lines=[]
    for support,enabled,hdr,style,debug in product((0,1),(0,1),(0,1),(0,1),(0,7,8,9)):
        active=bool(support and enabled and hdr and style and not debug)
        macro=dict(WATER_OPTICS=enabled,SCENE_COLOR_MODE=hdr,WATER_STYLE=style,DEBUG_VIEW=debug)
        if support:
            macro[FEATURE]=1
        for tiles,ssr in product((0,1),repeat=2):
            options=dict(macro,WATER_TRACE_TILES=tiles,WATER_SCREEN_REFLECTIONS=ssr)
            lines.append(['settings',str(int(active)),str(int(bool(support and (active or debug)))),
                          str(int(bool(active and tiles and ssr))),*(f'{k}={v}' for k,v in options.items())])
    variants=({'WATER_OPTICS':1,FEATURE:True},{'WATER_OPTICS':0,FEATURE:True},
              {'WATER_OPTICS':1},{'WATER_OPTICS':1,FEATURE:True,'DEBUG_VIEW':8})
    for index,opts in enumerate(variants):
        for path in sorted(SHADERS.glob('*.fsh')):
            name=path.stem
            if not name.startswith('gbuffers_') and name not in ('deferred','deferred1','composite'):
                continue
            active=index==0
            target='0'
            formats='-'
            if name=='deferred':
                target='0,5,6,7,8,9' if active else '0,5,6'
                if active:
                    formats='RGBA32F,RGBA8,R16F'
            elif name=='deferred1' and active:
                target='10'
                formats='R32F'
            elif name in WRITERS:
                target='0,1,2,8' if active else '0,1,2'
            elif name=='gbuffers_water' and (active or index==3):
                target='0,7,8' if active else '0,7'
                if index==3:
                    formats='RGBA32F'
            elif name.startswith('gbuffers_') and active:
                target='0,8'
            filename=f'{index}-{path.name}'
            (work/filename).write_text(configure(expand(path),opts),encoding='utf-8')
            lines.append(['shader',filename,target,formats])
    (work/'cases.tsv').write_text('\n'.join('\t'.join(row) for row in lines),encoding='utf-8')
    env=dict(os.environ,TEMP=str(work),TMP=str(work),TMPDIR=str(work))
    subprocess.run(['javac','-J-XX:-UsePerfData',f'-J-Djava.io.tmpdir={work}','-cp',cp,str(java)],
                   cwd=work,env=env,check=True)
    subprocess.run(['java','-XX:-UsePerfData',f'-Djava.io.tmpdir={work}','-cp',cp,'WaterDirectives',
                    str(work),str(SHADERS/'shaders.properties')],cwd=work,env=env,check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iris-jar', type=Path, required=True)
    parser.add_argument('--slf4j-jar', type=Path, required=True)
    args=parser.parse_args()
    parent=ROOT.parent.resolve()
    with TemporaryDirectory(prefix='aurora-iris-',dir=parent) as directory:
        work=Path(directory).resolve()
        if work.parent!=parent or not work.name.startswith('aurora-iris-'):
            raise ValueError('Unexpected scratch directory')
        verify(work,args.iris_jar,args.slf4j_jar)
