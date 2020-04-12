from apscheduler.schedulers.blocking import BlockingScheduler

from rq import Queue
from worker import conn

from musicdipity.music_worker import spawn_musicdipity_tasks

q = Queue(connection=conn)

sched = BlockingScheduler()

@sched.scheduled_job('interval', minutes=1)
def timed_job():
    print('This job is run every minute.')
    result = q.enqueue(spawn_musicdipity_tasks)


sched.start()