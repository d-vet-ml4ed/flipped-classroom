#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import numpy as np
import logging

from extractor.feature.feature import Feature

'''
The average time to solve a problem
'''
class TimeSolveProblem(Feature):

    def __init__(self, data, settings):
        super().__init__('time_solve_problem', data, settings)

    def compute(self):

        if len(self.data.index) == 0:
            logging.info('feature {} is invalid'.format(self.name))
            return Feature.INVALID_VALUE

        self.data['prev_event'] = self.data['event_type'].shift(1)
        self.data['prev_problem_id'] = self.data['problem_id'].shift(1)
        self.data['time_diff'] = self.data['date'].diff().dt.total_seconds()
        self.data = self.data.dropna(subset=['time_diff'])

        return np.mean(self.data.groupby(by='problem_id').sum()['time_diff'].values)
