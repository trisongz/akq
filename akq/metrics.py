# Forked from https://github.com/kpn/arq-prometheus/blob/main/arq_prometheus/client.py
# Source: arq_prometheus/client.py
# Author: kpn


import asyncio
import datetime
import logging
import re
from typing import Dict, Optional

import prometheus_client as prom
from akq.connections import ArqKeyDB
from akq.constants import default_queue_name, health_check_key_suffix

logger = logging.getLogger('akq.metrics')


async def read_health_check_key(
    keydb: ArqKeyDB,
    health_check_key: str,
) -> Optional[str]:
    data: Optional[str] = await keydb.get(health_check_key)
    return data


HEALTH_REGEX = 'j_complete=(?P<completed>[0-9]+).j_failed=(?P<failed>[0-9]+).j_retried=(?P<retried>[0-9]+).j_ongoing=(?P<ongoing>[0-9]+).queued=(?P<queued>[0-9]+)'  # noqa


class ArqPrometheusMetrics:
    """Provide Prometheus metrics based on the health check information.
    `ArqPrometheusMetrics` uses the redis provided by the arq ctx.
    ```
    async def startup(ctx):
        arq_prometheus = ArqPrometheusMetrics(
            ctx, delay=delay, enable_webserver=True
        )
        ctx['arq_prometheus'] = await arq_prometheus.start()
    async def shutdown(ctx):
        await ctx['arq_prometheus'].stop()
    class WorkerSettings:
        on_startup = startup
        on_shutdown = shutdown
        function = []  # your arq jobs
        ... # other settings
    ```
    See examples folder for more usage.
    """

    def __init__(
        self,
        ctx: dict,
        queue_name: str = default_queue_name,
        health_check_key: Optional[str] = None,
        delay: datetime.timedelta = datetime.timedelta(seconds=5),
        enable_webserver: bool = True,
        addr: str = '0.0.0.0',
        port: int = 8081,
        registry: prom.CollectorRegistry = prom.REGISTRY,
    ):
        """
        Args:
            ctx: arq context
            queue_name: name of the arq queue
            health_check_key: arq health key
            delay: a datetime.timedelta
            enable_webserver: set to True if you want a web server exposing the metrics
            addr: webserver address
            port: webserver port
            registry: the prometheus registry, usually you do not have to override this
        """
        self.ctx = ctx
        self._metrics_task: Optional[asyncio.Task] = None

        # Built based on arq's own health check, but that function returns an int
        # instead of the read value from redis
        # See https://github.com/samuelcolvin/arq/blob/master/arq/worker.py#L774
        self.queue_name = queue_name
        self.health_check_key = health_check_key or (
            queue_name + health_check_key_suffix
        )

        # prometheus-arq config
        self.health_prog = re.compile(HEALTH_REGEX)
        self.delay = delay.total_seconds()

        # Web server config
        self.enable_webserver = enable_webserver
        self.addr = addr
        self.port = port

        # Prometheus config and metrics
        self.registry = registry

        self.jobs_completed = prom.Gauge(
            'arq_jobs_completed',
            'The number of jobs completed.',
            registry=registry,
        )
        self.jobs_failed = prom.Gauge(
            'arq_jobs_failed',
            'The total number of errored jobs.',
            registry=registry,
        )

        self.jobs_retried = prom.Gauge(
            'arq_jobs_retried',
            'The total number of retried jobs.',
            registry=registry,
        )

        self.jobs_ongoing = prom.Gauge(
            'arq_jobs_ongoing',
            'The number of jobs in progress.',
            registry=registry,
        )

        self.jobs_queued = prom.Gauge(
            'arq_queued_inprogress',
            'The number of jobs in progress.',
            registry=registry,
        )

    async def start(self):
        """Initialize loop and maybe webserver."""
        logger.info('[metrics] Initializing prometheus...')
        logger.debug(f'[metrics] `queue_name`: "{self.queue_name}"')
        logger.debug(f'[metrics] `health_check_key`: "{self.health_check_key}"')

        await self.start_metrics_task()
        if self.enable_webserver:
            logger.info('[metrics] Starting webserver in separate thread...')
            self.start_webserver()
            logger.info('[metrics] Webserver up and running!')
        logger.info('[metrics] Init complete!')
        return self

    async def stop(self):
        """Terminate the metrics task"""
        logger.info('[metrics] Stopping prometheus...')
        if self._metrics_task is not None:
            self._metrics_task.cancel()
        logger.info('[metrics] Stop complete!')

    async def metrics_task(self):
        while True:
            # Sleep first to let worker initialize itself.
            await asyncio.sleep(self.delay)
            logger.debug(f'[metrics] Gathering metrics (interval {self.delay}s)')

            keydb = self.ctx['keydb']
            results = await read_health_check_key(keydb, self.health_check_key)

            if results is None:
                logger.warning(
                    '[metrics] Health key could not be read, value is `None`.\n'
                    'Possible causes:\n'
                    '- health key has not been initialized by the worker yet\n'
                    '- `health_check_key` or `queue_name` settings may be wrong\n'
                    'Retrying...'
                )
                continue
            logger.debug(f'[metrics] {results}')
            parsed = self.parse(results)
            if parsed is None:
                logger.warning('[metrics] unexpected health check result')
                continue

            await asyncio.get_event_loop().run_in_executor(
                None, self.generate_metrics, parsed
            )

    def parse(self, results: str) -> Optional[Dict[str, int]]:
        """Read health check and return a parsed dict."""
        parsed = self.health_prog.search(results)
        if parsed is None:
            return None
        return {key: int(value) for key, value in parsed.groupdict().items()}

    async def start_metrics_task(self) -> None:
        logger.debug('[metrics] Starting metrics task...')

        async def func_wrapper() -> None:
            """Wrapper function for a better error mesage when coroutine fails"""
            try:
                await self.metrics_task()
            except Exception as e:
                logger.error(e)

        self._metrics_task = asyncio.create_task(func_wrapper())

    def generate_metrics(self, data: dict):
        self.jobs_completed.set(data['completed'])
        self.jobs_failed.set(data['failed'])
        self.jobs_retried.set(data['retried'])
        self.jobs_ongoing.set(data['ongoing'])
        self.jobs_queued.set(data['queued'])

    def start_webserver(self) -> None:
        """Start web server in a different thread."""
        prom.start_wsgi_server(self.port, addr=self.addr, registry=self.registry)
        logger.info(f'[metrics] Running at: http://{self.addr}:{self.port}/')
