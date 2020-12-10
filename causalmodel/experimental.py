import numpy as np
from .potentialoutcome import PotentialOutcome
from .designs import CRD
import statsmodels.api as sm 


class Experimental(PotentialOutcome):
    """Main class for experimental data."""
    
    def __init__(self, Y, Z, X=None, design=CRD()):
        """For experimental data, covariates and an instance of design class
        are optional."""
        if X is None:
            X = np.ones(Y.shape)
        super(self.__class__, self).__init__(Y,Z,X)
        self.design = design
        self.design.get_params_via_obs(Z)
        self.stats = None
        self.cal_stats = None
        
        
    def estimate(self):
        """Default estimation is a difference-in-mean estimator."""
        return self.est_via_dm()
    
    
    def est_via_dm(self):
        """Difference-in-mean estimator"""
        self.cal_stats = lambda Z: np.mean(self.data.Y[Z==1]) - np.mean(self.data.Y[Z==0])
        self.stats = self.cal_stats(self.data.Z)
        ate, se = self.cal_dm(self.data.Z, self.data.Y)
        return self._get_results(ate, se)
        
    
    def est_via_strata(self, strata):
        """
        Estimate with stratified data.

        Parameters
        ----------
        strata : numpy.ndarray
            Labels of groups.


        Returns
        -------
        result class

        """
        if len(strata) != self.data.n:
            raise RuntimeError("input doesn't have the same length as the data.")
        if type(strata) != np.ndarray:
            raise TypeError("input must be numpy array.")
        ate_list = list()
        se_list = list()
        for l in set(strata):
            w = np.mean(strata==l)
            ate_s, se_s = self.cal_dm(self.data.Z[strata==l], self.data.Y[strata==l])
            ate_list.append(ate_s*w)
            se_list.append((se_s**2)*(w**2))
        ate = np.sum(ate_list)
        se = np.sqrt(np.sum(se_list))
        return self._get_results(ate, se)

    
    def est_via_ancova(self):
        """Estimate with Fisher's ancova."""
        Z = self.data.Z.reshape(-1,1)
        regressor = np.concatenate((np.ones((self.data.n,1)), Z, 
                              self.data.X, self.data.X * Z), axis=1)
        ols = sm.OLS(self.data.Y, regressor).fit()
        ate = ols.params[1]
        se = ols.HC0_se[1]
        return self._get_results(ate, se)
    
    
    def test_via_fisher(self, n=1000):
        """Compute p-value via Fisher Randomization Test."""
        T_s = np.zeros(n)
        for i in range(n):
            Z_s = self.design.draw(self.data.n)
            T_s[i] = self.cal_stats(Z_s)
        pval = min(np.mean(T_s > self.stats), np.mean(T_s < self.stats))
        return pval
    
    
    def cal_dm(self, Z, Y):
        """Helper function to calculate difference-in-mean"""
        ate = np.mean(Y[Z==1]) - np.mean(Y[Z==0])
        v1 = np.var(Y[Z==1])
        v2 = np.var(Y[Z==0])
        se = np.sqrt(v1/np.sum(Z==1)+ v2/np.sum(Z==0))
        return ate, se
    
