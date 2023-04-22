__all__ = ("MassFuncSheth99",)

import numpy as np

from ... import check, lib, warn_api
from . import MassFunc


class MassFuncSheth99(MassFunc):
    r"""Halo mass function by Sheth & Tormen (1999) :arXiv:astro-ph/9901122.
    Valid for FoF masses only.

    The mass function takes the form

    .. math::

        n(M, z) = A \, \nu \, \left( 1 + \left(a\nu^2\right)^{-p} \right) \,
        \exp{\left( -\frac{a\nu^2}{2} \right)},

    where :math:`\nu \equiv \delta_c/\sigma`, :math:`A` is the normalization
    factor which makes the integral of :math:`f(\nu){\rm d}\nu` to be unity,
    and :math:`(a, p) = (0.707, 0.3)` are fitted parameters.

    Parameters
    ----------
    mass_def : :class:`~pyccl.halos.massdef.MassDef` or str, optional
        Mass definition for this :math:`n(M)` parametrization.
        The default is :math:`{\rm FoF}`.
    mass_def_strict : bool, optional
        If True, only allow the mass definitions for which this halo bias
        relation was fitted, and raise if another mass definition is passed.
        If False, do not check for model consistency for the mass definition.
        The default is True.
    use_delta_c_fit : bool, optional
        If True, use the formula for :math:`\delta_{\rm c}` given by the
        fit of Nakamura & Suto (1997). If False, use
        :math:`\delta_{\rm c} \simeq 1.68647` given by spherical collapse
        theory. The default is False.
    """
    __repr_attrs__ = __eq_attrs__ = (
        "mass_def", "mass_def_strict", "use_delta_c_fit",)
    name = 'Sheth99'

    @warn_api
    def __init__(self, *,
                 mass_def="fof",
                 mass_def_strict=True,
                 use_delta_c_fit=False):
        self.use_delta_c_fit = use_delta_c_fit
        super().__init__(mass_def=mass_def, mass_def_strict=mass_def_strict)

    def _check_mass_def_strict(self, mass_def):
        return mass_def.Delta != "fof"

    def _setup(self):
        self.A = 0.21615998645
        self.p = 0.3
        self.a = 0.707

    def _get_fsigma(self, cosmo, sigM, a, lnM):
        if self.use_delta_c_fit:
            status = 0
            delta_c, status = lib.dc_NakamuraSuto(cosmo.cosmo, a, status)
            check(status, cosmo=cosmo)
        else:
            delta_c = 1.68647

        nu = delta_c / sigM
        return nu * self.A * (1. + (self.a * nu**2)**(-self.p)) * (
            np.exp(-self.a * nu**2/2.))
