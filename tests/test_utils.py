import logging
import re
from datetime import timedelta

import pytest
from aiokeydb.exceptions import ConnectionError, ResponseError
from pydantic import BaseModel, validator

import akq.typing
import akq.utils
from akq.connections import KeyDBSettings, log_keydb_info

from .conftest import SetEnv


def test_settings_changed():
    settings = KeyDBSettings(port=123)
    assert settings.port == 123
    assert (
        "KeyDBSettings(host='localhost', port=123, database=0, username=None, password=None, ssl=None, conn_timeout=1, "
        "conn_retries=5, conn_retry_delay=1, sentinel=False, sentinel_master='mymaster')"
    ) == str(settings)


async def test_keydb_timeout(mocker, create_pool):
    mocker.spy(akq.utils.asyncio, 'sleep')
    with pytest.raises(ConnectionError):
        await create_pool(KeyDBSettings(port=0, conn_retry_delay=0))
    assert akq.utils.asyncio.sleep.call_count == 5


@pytest.mark.skip(reason='this breaks many other tests as low level connections remain after failed connection')
async def test_keydb_sentinel_failure(create_pool, cancel_remaining_task, mocker):
    settings = KeyDBSettings()
    settings.host = [('localhost', 6379), ('localhost', 6379)]
    settings.sentinel = True
    with pytest.raises(ResponseError, match='unknown command `SENTINEL`'):
        await create_pool(settings)


async def test_keydb_success_log(caplog, create_pool):
    caplog.set_level(logging.INFO)
    settings = KeyDBSettings()
    pool = await create_pool(settings)
    assert 'KeyDB connection successful' not in [r.message for r in caplog.records]
    await pool.close(close_connection_pool=True)

    pool = await create_pool(settings, retry=1)
    assert 'KeyDB connection successful' in [r.message for r in caplog.records]
    await pool.close(close_connection_pool=True)


async def test_keydb_log(create_pool):
    keydb = await create_pool(KeyDBSettings())
    await keydb.flushall()
    await keydb.set(b'a', b'1')
    await keydb.set(b'b', b'2')

    log_msgs = []

    def _log(s):
        log_msgs.append(s)

    await log_keydb_info(keydb, _log)
    assert len(log_msgs) == 1
    print(log_msgs[0])
    assert re.search(r'redis_version=\d\.', log_msgs[0]), log_msgs
    assert log_msgs[0].endswith(' db_keys=2')


def test_truncate():
    assert akq.utils.truncate('123456', 4) == '123…'


def test_args_to_string():
    assert akq.utils.args_to_string((), {'d': 4}) == 'd=4'
    assert akq.utils.args_to_string((1, 2, 3), {}) == '1, 2, 3'
    assert akq.utils.args_to_string((1, 2, 3), {'d': 4}) == '1, 2, 3, d=4'


@pytest.mark.parametrize(
    'input,output', [(timedelta(days=1), 86_400_000), (42, 42000), (42.123, 42123), (42.123_987, 42124), (None, None)]
)
def test_to_ms(input, output):
    assert akq.utils.to_ms(input) == output


@pytest.mark.parametrize('input,output', [(timedelta(days=1), 86400), (42, 42), (42.123, 42.123), (None, None)])
def test_to_seconds(input, output):
    assert akq.utils.to_seconds(input) == output


def test_typing():
    assert 'OptionType' in akq.typing.__all__


def test_keydb_settings_validation():
    class Settings(BaseModel):
        keydb_settings: KeyDBSettings

        @validator('keydb_settings', always=True, pre=True)
        def parse_keydb_settings(cls, v):
            if isinstance(v, str):
                return KeyDBSettings.from_dsn(v)
            else:
                return v

    s1 = Settings(keydb_settings='keydb://foobar:123/4')
    assert s1.keydb_settings.host == 'foobar'
    assert s1.keydb_settings.port == 123
    assert s1.keydb_settings.database == 4
    assert s1.keydb_settings.ssl is False

    s2 = Settings(keydb_settings={'host': 'testing.com'})
    assert s2.keydb_settings.host == 'testing.com'
    assert s2.keydb_settings.port == 6379

    with pytest.raises(ValueError, match='instance of SSLContext expected'):
        Settings(keydb_settings={'ssl': 123})

    s3 = Settings(keydb_settings={'ssl': True})
    assert s3.keydb_settings.host == 'localhost'
    assert s3.keydb_settings.ssl is True

    s4 = Settings(keydb_settings='keydb://user:pass@foobar')
    assert s4.keydb_settings.host == 'foobar'
    assert s4.keydb_settings.username == 'user'
    assert s4.keydb_settings.password == 'pass'


def test_ms_to_datetime_tz(env: SetEnv):
    akq.utils.get_tz.cache_clear()
    env.set('ARQ_TIMEZONE', 'Asia/Shanghai')
    env.set('TIMEZONE', 'Europe/Berlin')  # lower priority as per `timezone_keys`
    dt = akq.utils.ms_to_datetime(1_647_345_420_000)  # 11.57 UTC
    assert dt.isoformat() == '2022-03-15T19:57:00+08:00'
    assert dt.tzinfo.zone == 'Asia/Shanghai'

    # should have no effect due to caching
    env.set('ARQ_TIMEZONE', 'Europe/Berlin')
    dt = akq.utils.ms_to_datetime(1_647_345_420_000)
    assert dt.isoformat() == '2022-03-15T19:57:00+08:00'


def test_ms_to_datetime_no_tz(env: SetEnv):
    akq.utils.get_tz.cache_clear()
    dt = akq.utils.ms_to_datetime(1_647_345_420_000)  # 11.57 UTC
    assert dt.isoformat() == '2022-03-15T11:57:00+00:00'

    # should have no effect due to caching
    env.set('ARQ_TIMEZONE', 'Europe/Berlin')
    dt = akq.utils.ms_to_datetime(1_647_345_420_000)
    assert dt.isoformat() == '2022-03-15T11:57:00+00:00'


def test_ms_to_datetime_tz_invalid(env: SetEnv, caplog):
    akq.utils.get_tz.cache_clear()
    env.set('ARQ_TIMEZONE', 'foobar')
    caplog.set_level(logging.WARNING)
    dt = akq.utils.ms_to_datetime(1_647_345_420_000)
    assert dt.isoformat() == '2022-03-15T11:57:00+00:00'
    assert "unknown timezone: 'foobar'\n" in caplog.text
