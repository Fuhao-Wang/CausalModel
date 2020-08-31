import numpy as np
from scipy.stats import norm
from model import Model
from result import Result
import warnings
from LearningModels import LogisticRegression


class PotentialOutcome(Model):
    
    
    def __init__(self, Y, Z, X):
        
        self.data = POdata(Y, Z, X)
        self.propensity = None
        self.treated_pred = None
        self.control_pred = None
        self.result = None
        super(self.__class__, self).__init__(self.data, self.result)
        self.eps = 1e-4
    
    
    def est_propensity(self, PropensityModel):
        # Estiamte propensity score with learning model for propensity score: 
        # Z ~ X (binary classfication)
        prop_model = PropensityModel()
        prop_model.fit(self.data.X, self.data.Z)
        return prop_model.insample_proba()
    
        
    def estimate(self):
        return self.est_via_ipw(LogisticRegression)
    
    
    def est_via_ipw(self, PropensityModel, propensity=None, normalize=True):
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
        
        return self._get_results(G)
    
    
    def est_via_aipw(self, OutcomeModel, PropensityModel, treated_pred=None, 
                     control_pred=None, propensity=None):
        # compute conditional mean and propensity score
        if treated_pred is not None:
            self.treated_pred = treated_pred
        else:
            treated_model = OutcomeModel()
            treated_model.fit(self.data.Xt, self.data.Yt)
            self.treated_pred = treated_model.predict(self.data.X)
            
        if control_pred is not None:
            self.control_pred = control_pred
        else:
            control_model = OutcomeModel()
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
        
        return self._get_results(G)
    
    
    def _fix_propensity(self):
        if self.propensity is not None:
            num_bad_prop = np.sum((self.propensity*(1-self.propensity)) == 0)
            if num_bad_prop > 0:
                self.propensity[self.propensity == 0] += self.eps
                self.propensity[self.propensity == 1] -= self.eps
                warnings.warn("Propensity scores has {} number of 0s or 1s."
                              .format(num_bad_prop))
    
    
    def _get_results(self, G):
        ate = np.mean(G)
        se = np.sqrt(np.var(G) / (len(G)-1))
        self.result = Result(average_treatment_effect=ate,
                             standard_error=se,
                             z=ate/se,
                             p_value=((1 - norm.cdf(ate/se))*2),
                             confidence_interval=(ate - 1.96*se, ate+1.96*se))
        return self.result

    
    
class POdata(object):
    
    
    def __init__(self, Y, Z, X):
        self.Y = Y
        self.Z = Z
        self.X = X
        if self.verify_data():
            self.n = self.get_n()
            self.idx_t = self.Z == 1
            self.idx_c = self.Z == 0
            self.Yc = self.get_Yc()
            self.Yt = self.get_Yt()
            self.Xc = self.get_Xc()
            self.Xt = self.get_Xt()
        else:
            import logging
            logging.error("The data provided should be ndarray of the same length")
            
    
    def get_n(self):
        return len(self.Y)
    
    
    def get_Yc(self):
        return self.Y[self.idx_c]
    
    
    def get_Yt(self):
        return self.Y[self.idx_t]
    
    
    def get_Xc(self):
        return self.X[self.idx_c]
    
    
    def get_Xt(self):
        return self.X[self.idx_t]
    
    
    def verify_data(self):
        if not (isinstance(self.X, np.ndarray) \
                and isinstance(self.Y, np.ndarray) \
                and isinstance(self.Z, np.ndarray)):
            return False
        if not len(self.Y) == len(self.Z) == len(self.X):
            return False
        return True
