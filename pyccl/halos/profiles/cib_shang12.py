from ...base import warn_api
from .profile_base import HaloProfileCIB
from .nfw import HaloProfileNFW
import numpy as np
from scipy.integrate import simpson
from scipy.special import lambertw


__all__ = ("HaloProfileCIBShang12",)


class HaloProfileCIBShang12(HaloProfileCIB):
    """ CIB profile implementing the model by Shang et al.
    (2012MNRAS.421.2832S).

    The parametrization for the mean profile is:

    .. math::
        j_\\nu(r) = \\frac{1}{4\\pi}
        \\left(L^{\\rm cen}_{\\nu(1+z)}(M)+
        L^{\\rm sat}_{\\nu(1+z)}u_{\\rm sat}(r|M)
        \\right),

    where the luminosity from centrals and satellites is
    modelled as:

    .. math::
        L^{\\rm cen}_{\\nu}(M) = L^{\\rm gal}_\\nu(M)\\,
        N_{\\rm cen}(M),

    .. math::
        L^{\\rm sat}_{\\nu}(M) = \\int_{M_{\\rm min}}^{M} dm
        \\frac{dN_{\\rm sub}}{dm}\\,L^{\\rm gal}_\\nu(m).

    Here, :math:`dN_{\\rm sub}/dm` is the subhalo mass function,
    :math:`u_{\\rm sat}` is the satellite galaxy density profile
    (modelled as a truncated NFW profile), and the infrared
    galaxy luminosity is parametrized as

    .. math::
        L^{\\rm gal}_{\\nu}(M,z)=L_0(1+z)^{s_z}\\,
        \\Sigma(M)\\,S_\\nu,

    where the mass dependence is lognormal

    .. math::
        \\Sigma(M) = \\frac{M}{\\sqrt{2\\pi\\sigma_{LM}^2}}
        \\exp\\left[-\\frac{\\log_{10}^2(M/M_{\\rm eff})}
        {2\\sigma_{LM}^2}\\right],

    and the spectrum is a modified black-body law

    .. math::
        S_\\nu \\propto\\left\\{
        \\begin{array}{cc}
           \\nu^\\beta\\,B_\\nu(T_d) & \\nu < \\nu_0 \\\\
           \\nu^\\gamma & \\nu \\geq \\nu_0
        \\end{array}
        \\right.,

    with the normalization fixed by :math:`S_{\\nu_0}=1`,
    and :math:`\\nu_0` defined so the spectrum has a continuous
    derivative for all :math:`\\nu`.

    Finally, the dust temperature is assumed to have a redshift
    dependence of the form :math:`T_d=T_0(1+z)^\\alpha`.

    Args:
        concentration (:obj:`Concentration`): concentration-mass
            relation to use with this profile.
        nu_GHz (float): frequency in GHz.
        alpha (float): dust temperature evolution parameter.
        T0 (float): dust temperature at :math:`z=0` in Kelvin.
        beta (float): dust spectral index.
        gamma (float): high frequency slope.
        s_z (float): luminosity evolution slope.
        log10meff (float): log10 of the most efficient mass.
        sigLM (float): logarithmic scatter in mass.
        Mmin (float): minimum subhalo mass.
        L0 (float): luminosity scale (in
            :math:`{\\rm Jy}\\,{\\rm Mpc}^2\\,M_\\odot^{-1}`).
    """
    __repr_attrs__ = (
        "concentration", "nu", "alpha", "T0", "beta", "gamma", "s_z",
        "l10meff", "sigLM", "Mmin", "L0", "precision_fftlog", "normprof")
    _one_over_4pi = 0.07957747154

    @warn_api(pairs=[("concentration", "concentration")])
    def __init__(self, *, concentration, nu_GHz, alpha=0.36, T0=24.4,
                 beta=1.75, gamma=1.7, s_z=3.6, log10meff=12.6, sigLM=0.707,
                 Mmin=1E10, L0=6.4E-8):

        self.nu = nu_GHz
        self.alpha = alpha
        self.T0 = T0
        self.beta = beta
        self.gamma = gamma
        self.s_z = s_z
        self.l10meff = log10meff
        self.sigLM = sigLM
        self.Mmin = Mmin
        self.L0 = L0
        self.concentration = concentration
        self.pNFW = HaloProfileNFW(concentration=concentration)
        super().__init__()

    def dNsub_dlnM_TinkerWetzel10(self, Msub, Mparent):
        """Subhalo mass function of Tinker & Wetzel (2010ApJ...719...88T)

        Args:
            Msub (float or array_like): sub-halo mass (in solar masses).
            Mparent (float): parent halo mass (in solar masses).

        Returns:
            float or array_like: average number of subhalos.
        """
        return 0.30*(Msub/Mparent)**(-0.7)*np.exp(-9.9*(Msub/Mparent)**2.5)

    def update_parameters(self, nu_GHz=None,
                          alpha=None, T0=None, beta=None, gamma=None,
                          s_z=None, log10meff=None, sigLM=None,
                          Mmin=None, L0=None):
        """ Update any of the parameters associated with
        this profile. Any parameter set to `None` won't be updated.

        Args:
            nu_GHz (float): frequency in GHz.
            alpha (float): dust temperature evolution parameter.
            T0 (float): dust temperature at :math:`z=0` in Kelvin.
            beta (float): dust spectral index.
            gamma (float): high frequency slope.
            s_z (float): luminosity evolution slope.
            log10meff (float): log10 of the most efficient mass.
            sigLM (float): logarithmic scatter in mass.
            Mmin (float): minimum subhalo mass.
            L0 (float): luminosity scale (in
                :math:`{\\rm Jy}\\,{\\rm Mpc}^2\\,M_\\odot^{-1}`).
        """
        if nu_GHz is not None:
            self.nu = nu_GHz
        if alpha is not None:
            self.alpha = alpha
        if T0 is not None:
            self.T0 = T0
        if beta is not None:
            self.beta = beta
        if gamma is not None:
            self.gamma = gamma
        if s_z is not None:
            self.s_z = s_z
        if log10meff is not None:
            self.l10meff = log10meff
        if sigLM is not None:
            self.sigLM = sigLM
        if Mmin is not None:
            self.Mmin = Mmin
        if L0 is not None:
            self.L0 = L0

    def _spectrum(self, nu, a):
        # h*nu_GHZ / k_B / Td_K
        h_GHz_o_kB_K = 0.0479924466
        Td = self.T0/a**self.alpha
        x = h_GHz_o_kB_K * nu / Td

        # Find nu_0
        q = self.beta+3+self.gamma
        x0 = q+np.real(lambertw(-q*np.exp(-q), k=0))

        def mBB(x):
            ex = np.exp(x)
            return x**(3+self.beta)/(ex-1)

        mBB0 = mBB(x0)

        def plaw(x):
            return mBB0*(x0/x)**self.gamma

        return np.piecewise(x, [x <= x0],
                            [mBB, plaw])/mBB0

    def _Lum(self, l10M, a):
        # Redshift evolution
        phi_z = a**(-self.s_z)
        # Mass dependence
        # M/sqrt(2*pi*sigLM^2)
        sig_pref = 10**l10M/(2.50662827463*self.sigLM)
        sigma_m = sig_pref * np.exp(-0.5*((l10M - self.l10meff)/self.sigLM)**2)
        return self.L0*phi_z*sigma_m

    def _Lumcen(self, M, a):
        Lum = self._Lum(np.log10(M), a)
        Lumcen = np.heaviside(M-self.Mmin, 1)*Lum
        return Lumcen

    def _Lumsat(self, M, a):
        if not np.max(M) > self.Mmin:
            return np.zeros_like(M)

        res = np.zeros_like(M)
        M_use = M[M >= self.Mmin, None]
        logM = np.log10(M_use)
        LOGM_MIN = np.log10(self.Mmin)
        nm = max(2, 10*int(np.max(logM) - LOGM_MIN))
        msub = np.linspace(LOGM_MIN, np.max(logM), nm+1)[None, :]

        Lum = self._Lum(msub, a)
        dnsubdlnm = self.dNsub_dlnM_TinkerWetzel10(10**msub, M_use)
        integ = dnsubdlnm * Lum
        Lumsat = simpson(integ, x=np.log(10)*msub)
        res[-len(Lumsat):] = Lumsat
        return res

    def _real(self, cosmo, r, M, a, mass_def):
        M_use = np.atleast_1d(M)
        r_use = np.atleast_1d(r)

        # (redshifted) Frequency dependence
        spec_nu = self._spectrum(self.nu/a, a)

        Ls = self._Lumsat(M_use, a)
        ur = self.pNFW._real(cosmo, r_use, M_use,
                             a, mass_def)/M_use[:, None]

        prof = Ls[:, None]*ur*spec_nu*self._one_over_4pi

        if np.ndim(r) == 0:
            prof = np.squeeze(prof, axis=-1)
        if np.ndim(M) == 0:
            prof = np.squeeze(prof, axis=0)
        return prof

    def _fourier(self, cosmo, k, M, a, mass_def):
        M_use = np.atleast_1d(M)
        k_use = np.atleast_1d(k)

        # (redshifted) Frequency dependence
        spec_nu = self._spectrum(self.nu/a, a)

        Lc = self._Lumcen(M_use, a)
        Ls = self._Lumsat(M_use, a)
        uk = self.pNFW._fourier(cosmo, k_use, M_use,
                                a, mass_def)/M_use[:, None]

        prof = (Lc[:, None]+Ls[:, None]*uk)*spec_nu*self._one_over_4pi

        if np.ndim(k) == 0:
            prof = np.squeeze(prof, axis=-1)
        if np.ndim(M) == 0:
            prof = np.squeeze(prof, axis=0)
        return prof

    def _fourier_variance(self, cosmo, k, M, a, mass_def, nu_other=None):
        M_use = np.atleast_1d(M)
        k_use = np.atleast_1d(k)

        spec_nu1 = self._spectrum(self.nu/a, a)
        if nu_other is None:
            spec_nu2 = spec_nu1
        else:
            spec_nu2 = self._spectrum(nu_other/a, a)

        Lc = self._Lumcen(M_use, a)
        Ls = self._Lumsat(M_use, a)
        uk = self.pNFW._fourier(cosmo, k_use, M_use,
                                a, mass_def)/M_use[:, None]

        prof = Ls[:, None]*uk
        prof = 2*Lc[:, None]*prof + prof**2
        prof *= spec_nu1*spec_nu2*self._one_over_4pi**2

        if np.ndim(k) == 0:
            prof = np.squeeze(prof, axis=-1)
        if np.ndim(M) == 0:
            prof = np.squeeze(prof, axis=0)
        return prof
