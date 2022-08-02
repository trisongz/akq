import asyncio
from aiohttp import ClientSession
from akq import create_pool
from akq.connections import RedisSettings

async def download_content(ctx, url):
    session: ClientSession = ctx['session']
    async with session.get(url) as response:
        content = await response.text()
        print(f'{url}: {content:.80}...')
    return len(content)

async def startup(ctx):
    ctx['session'] = ClientSession()

async def shutdown(ctx):
    await ctx['session'].close()

async def main():
    redis = await create_pool(RedisSettings())
    for url in ('https://facebook.com', 'https://microsoft.com', 'https://github.com'):
        await redis.enqueue_job('download_content', url)

# WorkerSettings defines the settings to use when creating the work,
# it's used by the akq cli.
# For a list of available settings, see https://akq-docs.helpmanual.io/#akq.worker.Worker
class WorkerSettings:
    functions = [download_content]
    on_startup = startup
    on_shutdown = shutdown

if __name__ == '__main__':
    asyncio.run(main())
