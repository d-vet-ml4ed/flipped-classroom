#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import timedelta
from helper.htime import *

def get_sessions(data, max_session_length=120, min_session_action=3):
    sessions = []

    for index, group in data.groupby(['user_id']):

        group = group.sort_values('date')
        group['interval'] = (group['date'] - group['date'].shift(1)).total_seconds()
        group['session_id'] = (group['date'] - group['date'].shift(1) > pd.Timedelta(max_session_length, 'm')).cumsum() + 1

        session = group.groupby('session_id').count()
        session['user_id'] = index
        session['start_time'] = group.drop_duplicates(subset=['session_id'], keep='first')['date'].values
        session['end_time'] = group.drop_duplicates(subset=['session_id'], keep='last')['date'].values
        session['week'] = group.drop_duplicates(subset=['session_id'], keep='first')['week'].values
        session['weekday'] = group.drop_duplicates(subset=['session_id'], keep='first')['weekday'].values
        session['duration'] = session.apply(lambda row: (row['end_time'] - row['start_time']).total_seconds(), axis=1)
        session['event'] = group.groupby('session_id')['event_type'].apply(','.join).values
        session['interval'] = group.groupby('session_id')['interval'].apply(lambda x: list(x)[1:]).values
        session['no_events'] = session['date']

        sessions.append(session.reset_index())

    sessions = pd.concat(sessions, ignore_index=True)
    sessions = sessions[sessions['no_events'] >= min_session_action]

    return sessions

def get_videos_watched_on_right_week(data, settings):
    data = data[data['event_type'].str.contains('Video')]
    schedule = settings['course'].get_schedule()[['id', 'date']].rename(columns={'date': 'schedule_date'})
    first_views = data.merge(schedule, left_on=['video_id'], right_on=['id'])
    first_views['from_date'] = first_views['schedule_date'] - timedelta(weeks=1)
    filtered_first_views = first_views[(first_views['date'] >= first_views['from_date']) & (first_views['date'] <= first_views['schedule_date'])]
    return filtered_first_views.groupby(by='week').size().to_frame(name='count')

def get_week_video_total(settings):
    schedule = settings['course'].get_schedule()
    return schedule.groupby(by='week').size().to_frame(name='total')

def get_weekly_prop(data, settings):
    weekly_count = get_videos_watched_on_right_week(data, settings)
    weekly_total = get_week_video_total(settings)
    weekly_prop = weekly_total.merge(weekly_count, left_index=True, right_index=True, how='left')
    weekly_prop['count'] = weekly_prop['count'].fillna(0)
    return np.clip((weekly_prop['count'] / weekly_prop['total']).values, 0., 1.)

def get_weekly_prop_watched(data, settings):
    return get_weekly_prop(data.drop_duplicates(subset=['video_id']), settings)

def get_weekly_prop_replayed(data, settings):
    data['only_date'] = data['date'].dt.date
    data = data.drop_duplicates(subset=['video_id', 'only_date'])
    replayed_data = data[data.groupby('video_id')['video_id'].transform(len) > 1]
    return get_weekly_prop(replayed_data, settings)

def get_weekly_prop_interrupted(data, settings, end_period=60, stop_events=np.array(['Video.Pause', 'Video.Stop', 'Video.Load'])):
    schedule = settings['course'].get_schedule()[['id', 'duration']]

    data['time_diff'] = abs(data['date'].diff(-1).dt.total_seconds())
    data['next_video_id'] = data['video_id'].shift(-1)
    data = data.dropna(subset=['time_diff'])

    data = data.merge(schedule, left_on=['video_id'], right_on=['id'])
    data = data[(data['duration'] - data['current_time']) > end_period]

    break_too_long = (data['event_type'].isin(stop_events.tolist())) & (data['time_diff'] > end_period * end_period)
    break_then_other_video = (data['event_type'].isin(stop_events.tolist())) & (data['video_id'] != data['next_video_id'])
    event_other_video = (data['video_id'] != data['next_video_id']) & ((data['duration'] - data['current_time']) > data['time_diff'])
    data = data[break_too_long | break_then_other_video | event_other_video]

    return get_weekly_prop(data, settings)

def count_events(data, event):
    if 'Backward' in event:
        data = data[(data['event_type'] == 'Video.Seek') & (data['old_time'] > data['new_time'])]
    elif 'Forward' in event:
        data = data[(data['event_type'] == 'Video.Seek') & (data['old_time'] < data['new_time'])]
    else:
        data = data[data['event_type'].str.contains(event)]
    return len(data.index)

def get_time_speeding_up(data):
    data = data[(data['event_type'].str.contains('Video.'))]
    data['new_speed'] = data['new_speed'].fillna(method='ffill')
    data = data.dropna(subset=['new_speed'])
    data['time_diff'] = data['date'].diff().dt.total_seconds()
    data = data.dropna(subset=['time_diff'])
    data['prev_speed'] = data['new_speed'].shift(1)
    data = data.dropna(subset=['prev_speed'])
    return data[data['prev_speed'] > 1.0]['time_diff'].values

def similarity_days(wi, wj):
    m1, m2 = np.where(wi == 1)[0], np.where(wj == 1)[0]
    if len(m1) == 0 or len(m2) == 0:
        return 0
    return len(np.intersect1d(m1, m2)) / max(len(m1), len(m2))

def chi2_divergence(p1, p2, a1, a2):
    a = p1 - p2
    b = p1 + p2
    frac = np.divide(a, b, out=np.zeros(a.shape, dtype=float), where=b != 0)
    m1 = np.where(a1 == 1)[0]
    m2 = np.where(a2 == 1)[0]
    union = np.union1d(m1, m2)
    if (len(union) == 0): return np.nan
    return 1 - (1 / len(union)) * np.sum(np.square(frac))

def fourier_transform(Xi, f, n):
    return np.dot(np.exp(-2j * np.pi * f * n), Xi)

def get_sequence_from_course(course, seq_length=300):
    data = course.get_clickstream()

    users = course.get_students()
    weeks = np.arange(course.get_weeks())

    maps = {v:i for i, v in enumerate(data['event_type'].unique())}
    acts = np.zeros((len(users), len(weeks), seq_length))
    tims = np.zeros((len(users), len(weeks), seq_length))

    for sid, user_id in enumerate(users):
        data = data[data['user_id'] == user_id].sort_values(by='date').copy()
        data['event_type_id'] = data['event_type'].apply(lambda x: maps[x])
        for wid in weeks:
            data_week = data[data['week'] == wid]
            if len(data_week) > 0:
                acts[sid, wid] = data_week['event_type_id'].values[:seq_length] if len(data_week) > seq_length else np.pad(data_week['event_type_id'].values, (0, seq_length - len(data_week)), 'constant')
                tims[sid, wid] = data_week['timestamp'].values[:seq_length] if len(data_week) > seq_length else np.pad(data_week['timestamp'].values, (0, seq_length - len(data_week)), 'constant')

    return acts, tims, maps


