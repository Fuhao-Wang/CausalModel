import numpy as np
from .potentialoutcome import PotentialOutcome
import warnings
from .LearningModels import LogisticRegression, OLS
from scipy.spatial.distance import cdist
from sklearn.model_selection import KFold


class Observational(PotentialOutcome):
    """ Estimate causal effects with observational data """
    
    def __init__(self, Y, Z, X):
        """
        Initialization with input data

        Parameters
        ----------
        Y : numpy.ndarray
            Outcomes or response.
        Z : numpy.ndarray
            Treatment vector (binary).
        X : numpy.ndarray
            Covariates.
            
        """
        
        super(self.__class__, self).__init__(Y,Z,X)
        self.propensity = None
        self.treated_pred = None
        self.control_pred = None
        self.eps = 1e-4
    
    
    def est_propensity(self, PropensityModel):
        """
        Estiamte propensity score

        Parameters
        ----------
        PropensityModel : LearningModels inherited from sklearn

        Returns
        -------
        Propensity score.

        """
        # Estiamte propensity score with learning model for propensity score: 
        # Z ~ X (binary classfication)
        prop_model = PropensityModel
        prop_model.fit(self.data.X, self.data.Z)
        return prop_model.insample_proba()
    
        
    def estimate(self):
        """ default estimation method""" 
        return self.est_via_ipw()
    
    
    def est_via_ipw(self, PropensityModel=LogisticRegression(), propensity=None, normalize=True):
        """
        Estimate average treatment effects with IPW method.

        Parameters
        ----------
        PropensityModel : LearningModel, optional
            Estimation model for propensity scores. The default is LogisticRegression().
        propensity : numpy.ndarray, optional
            Optional input for a given proensity score. The default is None.
        normalize : boolean, optional
            Normalize weights by 1 if True. The default is True.

        Returns
        -------
        Result class
            A Result object containning relevant statistics.

        """
        if propensity is not None:
            self.propensity = propensity
        else:
            self.propensity = self.est_propensity(PropensityModel)
            
        self._fix_propensity()
        # Compute Average Treatment Effect (ATE)
        w1 = self.data.Z/self.propensity
        w0 = (1-self.data.Z)/(1-self.propensity)
        if normalize:
            G = w1 * self.data.Y/(np.sum(w1)/self.data.n) - w0 * self.data.Y/(np.sum(w0)/self.data.n)
        else:
            G = w1 * self.data.Y - w0 * self.data.Y 
        
        ate = np.mean(G)
        se = np.sqrt(np.var(G) / (len(G)-1))
        return self._get_results(ate, se)
    
    
    def est_via_aipw(self, OutcomeModel=OLS(), PropensityModel=LogisticRegression(), 
                     treated_pred=None, control_pred=None, propensity=None):
        """ Similar to est_via_aipw except that need to specify the outcome model"""
        # compute conditional mean and propensity score
        if treated_pred is not None:
            self.treated_pred = treated_pred
        else:
            treated_model = OutcomeModel
            treated_model.fit(self.data.Xt, self.data.Yt)
            self.treated_pred = treated_model.predict(self.data.X)
            
        if control_pred is not None:
            self.control_pred = control_pred
        else:
            control_model = OutcomeModel
            control_model.fit(self.data.Xc, self.data.Yc)
            self.control_pred = control_model.predict(self.data.X)
            
        if propensity is not None:
            self.propensity = propensity
        else:
            self.propensity = self.est_propensity(PropensityModel)
            
        self._fix_propensity()
        # Compute Average Treatment Effect (ATE)
        G = (self.treated_pred - self.control_pred 
             + self.data.Z * (self.data.Y - self.treated_pred)/ self.propensity 
             - (1 - self.data.Z) * (self.data.Y - self.control_pred)/ (1-self.propensity))
        
        ate = np.mean(G)
        se = np.sqrt(np.var(G) / (len(G)-1))
        return self._get_results(ate, se)
        
    
    def est_via_matching(self, num_matches=1, num_matches_for_var=None, bias_adj=False):
        """
        Averge treatment effects with matching algorithm.

        Parameters
        ----------
        num_matches : int, optional
            Number of matched units. The default is 1.
        num_matches_for_var : int, optional
            Number of matched units for nonparametric variance estimation. The default is None.
        bias_adj : boolean, optional
            Include the adjustment of bias term if True. The default is False.

        Returns
        -------
        Result class
            A Result object containning relevant statistics.

        """
        Xt, Yt, Xc, Yc = self.data.Xt, self.data.Yt, self.data.Xc, self.data.Yc
        nt, nc, n = self.data.nt, self.data.nc, self.data.n
        M, J = num_matches, num_matches_for_var
        if J is None:
            J = M

        # standardizing the covariate matrices and match
        sd_Xt, sd_Xc = np.sqrt(np.var(Xt, axis=0)), np.sqrt(np.var(Xc, axis=0))
        Xt_scaled, Xc_scaled = Xt/sd_Xt, Xc/sd_Xc
        match_for_t, match_for_c = self.mat_match_mat(Xt_scaled, Xc_scaled, M), \
            self.mat_match_mat(Xc_scaled, Xt_scaled, M)
        
        # compute ate
        Yhat_c, Yhat_t = np.mean(Yt[match_for_c],axis=1), np.mean(Yc[match_for_t],axis=1)
        ITT_t, ITT_c = Yt - Yhat_t, Yhat_c - Yc
        Yhat1, Yhat0 = np.append(Yt, Yhat_c), np.append(Yhat_t, Yc)
        
        atc, att = ITT_c.mean(), ITT_t.mean()
        ate = (nc/n)*atc + (nt/n)*att
        
        # adjust for bias
        if bias_adj:
            mu0 = OLS().fit(Xc, Yc)
            mu1 = OLS().fit(Xt, Yt)
            mu0_t, mu0_c = mu0.predict(Xt), mu0.predict(Xc)
            mu1_t, mu1_c = mu1.predict(Xt), mu1.predict(Xc)
            match_for_0t = np.mean(mu0_c[match_for_t],axis=1)
            match_for_1c = np.mean(mu1_t[match_for_c],axis=1)
            BM = np.sum(mu0_t - match_for_0t)/n - np.sum(mu1_c - match_for_1c)/n
            ate -= BM
            
        # estimate variance
        Km = np.zeros(n)
        for row in match_for_c:
            Km[row] += 1
        for row in match_for_t:
            Km[row+nt] += 1
        
        # 1. match treated to treated, control to control
        match_tt, match_cc =  self.mat_match_mat(Xt_scaled, Xt_scaled, J+1), \
            self.mat_match_mat(Xc_scaled, Xc_scaled, J+1)
        Yhat_cc, Yhat_tt = np.mean(Yc[match_cc],axis=1), np.mean(Yt[match_tt],axis=1)
        Y, Y_close = np.append(Yt, Yc), np.append(Yhat_tt, Yhat_cc)
        # 2. estimate conditional variance
        sigmaXW = (J+1)/J*((Y - Y_close)**2)
        # 3. compute variance
        V1 = (Yhat1 - Yhat0 - ate)**2
        V2 = ((Km/M)**2 + (2*M-1)/M * Km/M)*sigmaXW
        V = np.mean(V1 + V2)
        
        se = np.sqrt(V/n)
        return self._get_results(ate, se)
    
    
    def est_via_dml(self, OutcomeModel=OLS(), TreatmentModel=LogisticRegression(),
                    Kfolds=2):
        """
        When the treatment is not binary, using double/debiased ML is preferable.

        Parameters
        ----------
        OutcomeModel : LearningModel, optional
            Prediction of the outcome model as Y = f(X) + U. The default is OLS().
        TreatmentModel : LearningModel, optional
            Prediction of the treatment model as Z = g(X) + V. The default is LogisticRegression().
        Kfolds : number of folds for sample splitting and cross-fitting. The default is 2.

        Returns
        -------
        None.

        """
        kf = KFold(n_splits=Kfolds)
        idx = np.arange(self.data.n)
        thetas = []
        for idx_train, idx_test in kf.split(idx):
            # estimating outcome model
            OutcomeModel.fit(self.data.X[idx_train], self.data.Y[idx_train])
            U = self.data.Y[idx_test] - OutcomeModel.predict(self.data.X[idx_test])
            # estimating treatment model
            TreatmentModel.fit(self.data.X[idx_train], self.data.Z[idx_train])
            V = self.data.Z[idx_test] - TreatmentModel.predict(self.data.X[idx_test])
            # calculate estimator for theta
            thetas.append(V.dot(U)/V.dot(self.data.Z[idx_test]))
        
    
    
    def _fix_propensity(self):
        """ add a small number 'eps' if propensity score is zero"""
        if self.propensity is not None:
            num_bad_prop = np.sum((self.propensity*(1-self.propensity)) == 0)
            if num_bad_prop > 0:
                self.propensity[self.propensity == 0] += self.eps
                self.propensity[self.propensity == 1] -= self.eps
                warnings.warn("Propensity scores has {} number of 0s or 1s."
                              .format(num_bad_prop))
    
    
    
    def mat_match_mat(self, X, Y, M):
        return np.array([self.arr_match_mat(Xi, Y, M) for Xi in X])
         
    
    def dist_arr_mat(self, Xi, X):
        diff = X - Xi
        return np.sum(diff**2,axis=1)
        
    
    def arr_match_mat(self, Xi, X, M):
        dist = self.dist_arr_mat(Xi, X)
        return np.argpartition(dist, M)[:M]
    
    
    def mat_match_mat2(self, X, Y, M):
        D = cdist(X, Y)
        return np.argpartition(D, M, axis=1)[:,:M]
