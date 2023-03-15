import numpy as np
import pytest
import pyccl as ccl
from pyccl import EmulatorObject
import warnings


def test_bounds_raises_warns():
    # malformed bounds
    bounds = {"a": [0, 1], "b": [1, 0]}
    with pytest.raises(ValueError):
        EmulatorObject(model=None, bounds=bounds)

    # out of bounds
    bounds = {"a": [0, 1], "b": [0, 1]}
    proposal = {"a": 0, "b": -1}
    emu = EmulatorObject(model=None, bounds=bounds)
    with pytest.raises(ValueError):
        emu.check_bounds(proposal)


def test_bounds_repr():
    bounds = {"a": [0, 1], "b": [0, 1]}
    emu = EmulatorObject(model=None, bounds=bounds)
    assert eval(repr(emu.bounds)) == emu.bounds.bounds


def test_bounds_types():
    # Test all the bounds types EmulatorObject can accept.
    # 0. We have already checked the dictionary in the previous tests.

    # 1. No bounds (handled internally by the emulator).
    emu = EmulatorObject(model=None, bounds=None)
    assert emu.bounds is emu.check_bounds is NotImplemented

    # 2. Callable.
    def check(bounds):
        pass
    emu = EmulatorObject(model=None, bounds=check)
    assert emu.bounds is NotImplemented
    assert emu.check_bounds is check

    # 3. Wrong type.
    with pytest.raises(ValueError):
        EmulatorObject(model=None, bounds="something_else")


def test_emulator_from_name_raises():
    # emulator does not exist
    with pytest.raises(ValueError):
        ccl.PowerSpectrumEmulator.from_name("hello_world")


def test_bacco_smoke():
    cosmo1 = ccl.Cosmology(Omega_c=0.25, Omega_b=0.05, h=0.67,
                           sigma8=0.81, n_s=0.96,
                           transfer_function="bacco")
    cosmo2 = ccl.Cosmology(Omega_c=0.25, Omega_b=0.05, h=0.67,
                           A_s=2.2315e-9, n_s=0.96,
                           transfer_function="bacco")
    assert np.allclose(cosmo1.sigma8(), cosmo2.sigma8(), rtol=1e-4)
    assert np.allclose(cosmo1.linear_matter_power(1, 1),
                       cosmo2.linear_matter_power(1, 1), rtol=2e-4)


def test_bacco_baryon_smoke():
    cosmo = ccl.CosmologyVanillaLCDM(baryons_power_spectrum="bacco",
                                     extra_parameters=None)
    with warnings.catch_warnings():
        # ignore Tensorflow-related warnings
        warnings.simplefilter("ignore")
        cosmo.compute_nonlin_power()


def test_bacco_linear_nonlin_equiv():
    # In this test we get the baryon-corrected NL power spectrum directly
    # from cosmo, and compare it with the NL where we have applied the
    # baryon correction afterwards.
    knl = np.geomspace(0.1, 5, 64)
    extras = {"bacco": {'M_c': 14, 'eta': -0.3, 'beta': -0.22,
                        'M1_z0_cen': 10.5, 'theta_out': 0.25,
                        'theta_inn': -0.86, 'M_inn': 13.4}
              }
    cosmo = ccl.CosmologyVanillaLCDM(matter_power_spectrum="bacco",
                                     baryons_power_spectrum="bacco",
                                     extra_parameters=extras)
    with warnings.catch_warnings():
        # filter Pk2D narrower range warning
        warnings.simplefilter("ignore")
        cosmo.compute_nonlin_power()
    pk0 = cosmo.get_nonlin_power().eval(knl, 1, cosmo)

    emu = ccl.PowerSpectrumEmulator.from_name("bacco")()
    with warnings.catch_warnings():
        # filter Pk2D narrower range warning
        warnings.simplefilter("ignore")
        pk1 = emu.get_pk_nonlin(cosmo)
        # NL + bar
        pk1 = cosmo.baryon_correct("bacco", pk1).eval(knl, 1, cosmo)

    assert np.allclose(pk0, pk1, rtol=5e-3)


def test_power_spectum_emulator_funcs():
    cosmo = ccl.CosmologyVanillaLCDM(transfer_function="bbks",
                                     matter_power_spectrum="halofit")
    cosmo.compute_linear_power()
    cosmo.compute_nonlin_power()

    class DummyEmu(ccl.PowerSpectrumEmulator):
        name = "dummy"

        def __init__(self):
            super().__init__()

        def _load_emu(self):
            pass

    # 1. Test for `get_pk_linear`.
    # does not have a `get_pk_linear` method
    with pytest.raises(NotImplementedError):
        emu = ccl.PowerSpectrumEmulator.from_name("dummy")()
        emu.get_pk_linear(cosmo)

    # 2. Tests for `get_pk_nonlin`.
    # does not have `_get_pk_nonlin` or `_get_nonlin_boost`
    with pytest.raises(NotImplementedError):
        emu = ccl.PowerSpectrumEmulator.from_name("dummy")()
        emu.get_pk_nonlin(cosmo)

    # we define a custom `_get_pk_nonlin`
    def _get_pk_nonlin(self, cosmo):
        pk = cosmo.get_nonlin_power()
        a_arr, lk_arr, pk_arr = pk.get_spline_arrays()
        return a_arr, np.exp(lk_arr), pk_arr

    DummyEmu._get_pk_nonlin = _get_pk_nonlin
    # doesn't raise an error now
    emu = ccl.PowerSpectrumEmulator.from_name("dummy")()
    emu.get_pk_nonlin(cosmo)

    # 2. Tests for `apply_nonlin_model`.
    pkl = cosmo.get_linear_power()
    pknl = cosmo.get_nonlin_power()  # test against this

    # we define a custom `_get_pk_linear`
    def _get_pk_linear(self, cosmo):
        pk = cosmo.get_linear_power()
        a_arr, lk_arr, pk_arr = pk.get_spline_arrays()
        return a_arr, np.exp(lk_arr), pk_arr

    DummyEmu._get_pk_linear = _get_pk_linear

    emu = ccl.PowerSpectrumEmulator.from_name("dummy")()
    pknl_emu = emu.apply_nonlin_model(cosmo, pk_linear=pkl)

    pk1 = pknl.get_spline_arrays()[-1]
    pk2 = pknl_emu.get_spline_arrays()[-1]
    assert np.allclose(pk1, pk2, 1e-16)

    # does not have any method -> raises error
    del DummyEmu._get_pk_linear, DummyEmu._get_pk_nonlin
    with pytest.raises(NotImplementedError):
        emu = ccl.PowerSpectrumEmulator.from_name("dummy")()
        emu.apply_nonlin_model(cosmo, pk_linear=pkl)


def test_power_spectrum_emulator_baryon_raises():
    cosmo = ccl.CosmologyVanillaLCDM()

    from . import PowerSpectrumBACCO
    emu = ccl.PowerSpectrumEmulator.from_name("bacco")()
    with warnings.catch_warnings():
        # filter Pk2D narrower range warning
        warnings.simplefilter("ignore")
        pk = emu.get_pk_nonlin(cosmo)
    func = PowerSpectrumBACCO._get_baryon_boost
    delattr(PowerSpectrumBACCO, "_get_baryon_boost")
    with pytest.raises(NotImplementedError):
        emu.include_baryons(cosmo, pk)

    # reset the emulator methods
    setattr(PowerSpectrumBACCO, "_get_baryon_boost", func)