"""Per-request SQL timings, including SQL executed by sync worker endpoints."""
from contextvars import ContextVar
from time import perf_counter
from sqlalchemy import event

timings=ContextVar('atlas_timings',default=None)

def instrument(engine):
    @event.listens_for(engine,'before_cursor_execute')
    def before(conn,cursor,statement,parameters,context,executemany):
        context.atlas_started=perf_counter()
    @event.listens_for(engine,'after_cursor_execute')
    def after(conn,cursor,statement,parameters,context,executemany):
        values=timings.get()
        if values is not None:
            values['db']=values.get('db',0)+(perf_counter()-context.atlas_started)*1000
