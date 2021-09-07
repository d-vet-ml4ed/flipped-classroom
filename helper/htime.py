#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import datetime
import pandas as pd
import numpy as np

def tmp2dt(x):
    return str2dt(datetime.utcfromtimestamp(x).strftime('%Y-%m-%d %H:%M:%S'))

def str2dt(ts, format='%Y-%m-%d %H:%M:%S'):
    return datetime.strptime(ts, format)

def dt2w(dt):
    return dt.strftime('%W')

def order_week(series, start_date):
    start_week = int(dt2w(str2dt(start_date)))
    nb_week = int(series.max()) + 1
    return series.apply(lambda w: str((int(w) - start_week) % nb_week)).values

def get_date(series):
    return series.apply(tmp2dt)

def get_weekday(series):
    return series.apply(lambda x: x.weekday())

# SyntaxWarning: "is not" with a literal. Did you mean "!="?
def w4s(user_events, start_date, course_type, max_course_weeks=20):
    user_events = user_events.copy()
    first_access = str(user_events['date'].min())
    start_date = first_access if first_access > start_date and course_type != 'flipped-classroom' else start_date
    user_events['week'] = order_week(user_events['date'].apply(dt2w), start_date).astype(int)
    return user_events[user_events['week'] < max_course_weeks]

## ASK MIRKO !!!
## Why min_actions = 10 (?)
def add_week(df, start_date, type, min_actions=0, min_week=4, max_week=20):
    user_events_lst = []
    for user_id, user_events in df.groupby(by='user_id'):
        if len(user_events.index) > min_actions and int(user_events['date'].apply(dt2w).max()) > min_week:
            user_events_lst.append(w4s(user_events, start_date, type, max_week))
    return pd.concat(user_events_lst)

def filter_range_dates(df, start_date, end_date):
    df = df[df['date'] >= str2dt(start_date)]
    df = df[df['date'] <= str2dt(end_date)] if end_date is not np.nan else df
    return df

# Why are we filtering the events? Doesn't this prevent us from computing
# the complete session time? And creating future features?
# I would not filter out any events
def filter_events(df, type=np.array(['Video.Pause', 'Video.Load',
'Video.Play', 'Video.Seek', 'Video.Stop', 'Video.SpeedChange', 'Problem.Check',
  'Forum.Load', 'Forum.Search', 'Forum.Thread.Delete',
  'Forum.Thread.Follow', 'Forum.Thread.Launch',
  'Forum.Thread.Unfollow', 'Forum.Thread.Update',
  'Forum.Thread.View', 'Forum.Unknown'])):
    df = df[df['event_type'].isin(type.tolist())].sort_values(by='date')
    if 'problem_id' in df.columns:
        df = df.drop_duplicates(subset=['problem_id', 'event_type', 'timestamp'], keep='first')
        df = df[~(df['event_type'].str.contains('Assignment'))]
    return df

def init_clickstream(df, type, start_date, end_date):
    df['date'] = get_date(df['timestamp'])
    df['weekday'] = get_weekday(df['date'])
    df = filter_range_dates(df, start_date, end_date)
    df = add_week(df, start_date, type)
    #df = filter_events(df)
    return df

def init_schedule(df, type, start_date, end_date):
    if type == 'flipped-classroom':
        df['date'] = df['date'].apply(lambda x: str2dt(x, '%Y-%m-%d'))
        df['weekday'] = get_weekday(df['date'])
        df = filter_range_dates(df, start_date, end_date)
        df = w4s(df, start_date, type)
    elif type == 'mooc':
        df['week'] = df['date']
    return df
