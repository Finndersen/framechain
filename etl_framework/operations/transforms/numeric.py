from etl_framework.operations.base import ScalarOperation, ScalarOrVectorOperation
import numpy as np
import math


class Floor(ScalarOrVectorOperation):
    """ Floor numeric values (round down)"""
    def __call__(self, value):
        if self.input_type == 'column':
            return np.floor(value)
        else:
            return math.floor(value)
