class Model(object):
    
    
    def __init__(self, data = None, result = None):
        self.data = data
        self.result = result
        
        
    def __repr__(self):
        """
        Return the string representation of the model object
        :return:
        """
        return "{}".format(self.__class__.__name__)
    
    
    def estimate(self):
        pass