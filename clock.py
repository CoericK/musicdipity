from apscheduler.schedulers.blocking import BlockingScheduler

from rq import Queue
from worker import conn

from musicdipity.spotify_utils import test_worker

q = Queue(connection=conn)

sched = BlockingScheduler()

@sched.scheduled_job('interval', minutes=3)
def timed_job():
    print('This job is run every three minutes.')
    result = q.enqueue(test_worker)


sched.start()