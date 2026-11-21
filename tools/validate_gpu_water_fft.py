"""Validate the complete compute graph and its actual graphics consumers."""
OPTIONS=dict(WATER_FFT=1,IRIS_FEATURE_COMPUTE_SHADERS=True,IRIS_FEATURE_CUSTOM_IMAGES=True)


def fft_tests(runner,cxx,plate=None):
    from validate_gpu_water_fft_dynamics import dynamics_tests
    from validate_gpu_water_underwater import producer_tests
    from validate_gpu_water_fft_filter import filter_tests
    report=dynamics_tests(runner,cxx)
    frames=report.pop('native_frames')
    report['observed_exit']=producer_tests(runner,frames[2]['field'])
    report['caustic_filter']=filter_tests(runner)
    if plate is not None:
        from validate_gpu_water_fft_production import spectral_views
        spectral_views_data={t:frame for t,frame in zip(report['times'],frames)}
        report['views']=spectral_views(runner,spectral_views_data,plate)
    return report
