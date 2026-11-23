import os
import redis
from redis.sentinel import Sentinel
import threading
import time
import pytest
from dotenv import load_dotenv
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RedisConnection:
    def __init__(self):
        """Redis Sentinel 연결 초기화"""
        load_dotenv()
        
        # 환경 변수 로드
        self.sentinel_hosts = self._parse_hosts(os.getenv('REDIS_SENTINEL_HOSTS'))
        self.service_name = os.getenv('REDIS_SENTINEL_SERVICE_NAME')
        self.password = os.getenv('REDIS_PASSWORD')
        self.db = int(os.getenv('REDIS_DB', 0))
        self.socket_timeout = float(os.getenv('REDIS_SOCKET_TIMEOUT', 5))
        self.socket_connect_timeout = float(os.getenv('REDIS_SOCKET_CONNECT_TIMEOUT', 5))
        self.max_connections = int(os.getenv('REDIS_MAX_CONNECTIONS', 10))
        
        # 환경 변수 확인 로그
        logger.info("=== Redis Sentinel 설정 ===")
        logger.info(f"Sentinel Hosts: {self.sentinel_hosts}")
        logger.info(f"Service Name: {self.service_name}")
        logger.info(f"DB: {self.db}")
        logger.info(f"Socket Timeout: {self.socket_timeout}s")
        
        # Sentinel 초기화 (Sentinel 자체 인증 포함)
        self.sentinel = Sentinel(
            self.sentinel_hosts,
            socket_timeout=self.socket_timeout,
            socket_connect_timeout=self.socket_connect_timeout,
            sentinel_kwargs={'password': self.password}  # Sentinel 인증
        )
        
        # Master 및 Slave 연결
        self.master = None
        self.slave = None
        self._connect()
    
    def _parse_hosts(self, hosts_str):
        """호스트 문자열을 튜플 리스트로 변환"""
        hosts = []
        for host in hosts_str.split(','):
            host = host.strip()
            if ':' in host:
                ip, port = host.split(':')
                hosts.append((ip, int(port)))
            else:
                hosts.append((host, 26379))  # 기본 sentinel 포트
        return hosts
    
    def _connect(self):
        """Redis Master/Slave 연결"""
        try:
            # Master 검색
            master_info = self.sentinel.discover_master(self.service_name)
            logger.info(f"Master 발견: {master_info}")
            
            # Slave 검색
            slaves_info = self.sentinel.discover_slaves(self.service_name)
            logger.info(f"Slaves 발견: {slaves_info}")
            
            # Master 연결
            self.master = self.sentinel.master_for(
                self.service_name,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                password=self.password,  # Redis 인증
                db=self.db,
                decode_responses=True,  # 자동 문자열 디코딩
                max_connections=self.max_connections
            )
            
            # Master 연결 확인
            self.master.ping()
            logger.info("Master 연결 성공")
            
            # Slave 연결 (읽기 전용)
            self.slave = self.sentinel.slave_for(
                self.service_name,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                password=self.password,  # Redis 인증
                db=self.db,
                decode_responses=True,  # 자동 문자열 디코딩
                max_connections=self.max_connections
            )
            
            # Slave 연결 확인
            self.slave.ping()
            logger.info("Slave 연결 성공")
            logger.info("=== Redis Sentinel 연결 완료 ===\n")
            
        except redis.exceptions.MasterNotFoundError as e:
            logger.error(f"Master 찾기 실패: {e}")
            logger.error(f"Sentinel에서 '{self.service_name}' 서비스를 찾을 수 없습니다")
            raise
        except redis.exceptions.ResponseError as e:
            logger.error(f"Redis 인증 오류: {e}")
            logger.error("비밀번호 또는 DB 번호를 확인하세요")
            raise
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Redis 연결 오류: {e}")
            logger.error("Redis 서버가 실행 중인지, 방화벽 설정을 확인하세요")
            raise
        except Exception as e:
            logger.error(f"알 수 없는 오류: {type(e).__name__}: {e}")
            raise
    
    def get_master(self):
        """Master 연결 반환"""
        return self.master
    
    def get_slave(self):
        """Slave 연결 반환"""
        return self.slave
    
    def get_master_info(self):
        """현재 Master 정보 반환"""
        return self.sentinel.discover_master(self.service_name)
    
    def get_slaves_info(self):
        """현재 Slave 정보 반환"""
        return self.sentinel.discover_slaves(self.service_name)
    
    def close(self):
        """연결 종료"""
        try:
            if self.master:
                self.master.close()
                logger.info("Master 연결 종료")
            if self.slave:
                self.slave.close()
                logger.info("Slave 연결 종료")
        except Exception as e:
            logger.error(f"연결 종료 중 오류: {e}")


class RedisPubSub:
    def __init__(self, redis_conn):
        """Redis Pub/Sub 초기화"""
        self.redis_conn = redis_conn
        self.master = redis_conn.get_master()
        # Pub/Sub는 Master 사용 (안정성)
        self.pubsub = self.master.pubsub()
        self.messages = []
        self.running = False
        self.thread = None
    
    def publish(self, channel, message):
        """메시지 발행"""
        try:
            result = self.master.publish(channel, message)
            logger.info(f"메시지 발행 - 채널: {channel}, 구독자: {result}명")
            return result
        except Exception as e:
            logger.error(f"메시지 발행 실패: {e}")
            raise
    
    def subscribe(self, *channels):
        """채널 구독"""
        try:
            self.pubsub.subscribe(*channels)
            logger.info(f"채널 구독 완료: {channels}")
        except Exception as e:
            logger.error(f"채널 구독 실패: {e}")
            raise
    
    def psubscribe(self, *patterns):
        """패턴 구독"""
        try:
            self.pubsub.psubscribe(*patterns)
            logger.info(f"패턴 구독 완료: {patterns}")
        except Exception as e:
            logger.error(f"패턴 구독 실패: {e}")
            raise
    
    def listen(self, timeout=None):
        """메시지 수신 시작 (백그라운드 스레드)"""
        self.running = True
        
        def _listen():
            try:
                for message in self.pubsub.listen():
                    if not self.running:
                        break
                    
                    msg_type = message['type']
                    
                    if msg_type == 'message':
                        self.messages.append(message)
                        logger.info(f"메시지 수신: [{message['channel']}] {message['data']}")
                    elif msg_type == 'pmessage':
                        self.messages.append(message)
                        logger.info(f"패턴 메시지 수신: [{message['pattern']}] {message['channel']}: {message['data']}")
                    elif msg_type in ['subscribe', 'psubscribe']:
                        logger.info(f"구독 확인: {message}")
                    
            except Exception as e:
                logger.error(f"메시지 수신 중 오류: {e}")
        
        self.thread = threading.Thread(target=_listen)
        self.thread.daemon = True
        self.thread.start()
        logger.info("메시지 수신 스레드 시작")
        
        if timeout:
            time.sleep(timeout)
    
    def stop_listening(self):
        """메시지 수신 중지"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        try:
            self.pubsub.close()
            logger.info("메시지 수신 중지")
        except Exception as e:
            logger.error(f"PubSub 종료 중 오류: {e}")
    
    def get_messages(self):
        """수신된 메시지 반환"""
        return self.messages
    
    def clear_messages(self):
        """수신된 메시지 초기화"""
        self.messages.clear()
        logger.info("메시지 버퍼 초기화")


# ==================== pytest 테스트 케이스 ====================

class TestRedisConnection:
    """Redis 연결 테스트"""
    
    @pytest.fixture
    def redis_conn(self):
        """Redis 연결 픽스처"""
        conn = RedisConnection()
        yield conn
        conn.close()
    
    def test_redis_connection(self, redis_conn):
        """Redis 연결 테스트"""
        master = redis_conn.get_master()
        slave = redis_conn.get_slave()
        
        # 연결 확인
        assert master.ping() == True
        assert slave.ping() == True
        
        # 기본 CRUD 테스트
        master.set('test_key', 'test_value')
        time.sleep(0.1)  # 복제 지연 고려
        
        value = slave.get('test_key')
        assert value == 'test_value'
        
        # 삭제
        master.delete('test_key')
        time.sleep(0.1)
        assert slave.get('test_key') is None
        
        logger.info("✓ Redis 연결 테스트 성공")
    
    def test_redis_data_operations(self, redis_conn):
        """Redis 데이터 조작 테스트"""
        master = redis_conn.get_master()
        slave = redis_conn.get_slave()
        
        # String 테스트
        master.set('string_key', 'string_value', ex=60)
        time.sleep(0.1)
        assert slave.get('string_key') == 'string_value'
        assert slave.ttl('string_key') > 0
        
        # Hash 테스트
        master.hset('hash_key', 'field1', 'value1')
        master.hset('hash_key', 'field2', 'value2')
        time.sleep(0.1)
        assert slave.hget('hash_key', 'field1') == 'value1'
        assert slave.hgetall('hash_key') == {'field1': 'value1', 'field2': 'value2'}
        
        # List 테스트
        master.lpush('list_key', 'item1', 'item2', 'item3')
        time.sleep(0.1)
        assert slave.llen('list_key') == 3
        assert slave.lrange('list_key', 0, -1) == ['item3', 'item2', 'item1']
        
        # Set 테스트
        master.sadd('set_key', 'member1', 'member2', 'member3')
        time.sleep(0.1)
        assert slave.scard('set_key') == 3
        assert slave.sismember('set_key', 'member1') == True
        
        # Sorted Set 테스트
        master.zadd('zset_key', {'member1': 1, 'member2': 2, 'member3': 3})
        time.sleep(0.1)
        assert slave.zcard('zset_key') == 3
        assert slave.zscore('zset_key', 'member2') == 2.0
        
        # 정리
        master.delete('string_key', 'hash_key', 'list_key', 'set_key', 'zset_key')
        
        logger.info("✓ Redis 데이터 조작 테스트 성공")
    
    def test_redis_pipeline(self, redis_conn):
        """Redis Pipeline 테스트"""
        master = redis_conn.get_master()
        
        # Pipeline으로 여러 명령 한번에 실행
        pipe = master.pipeline()
        pipe.set('pipe_key1', 'value1')
        pipe.set('pipe_key2', 'value2')
        pipe.set('pipe_key3', 'value3')
        pipe.get('pipe_key1')
        pipe.get('pipe_key2')
        results = pipe.execute()
        
        assert results[3] == 'value1'
        assert results[4] == 'value2'
        
        # 정리
        master.delete('pipe_key1', 'pipe_key2', 'pipe_key3')
        
        logger.info("✓ Redis Pipeline 테스트 성공")
    
    def test_sentinel_info(self, redis_conn):
        """Sentinel 정보 확인 테스트"""
        master_info = redis_conn.get_master_info()
        slaves_info = redis_conn.get_slaves_info()
        
        assert master_info is not None
        assert len(master_info) == 2  # (ip, port)
        assert isinstance(slaves_info, list)
        
        logger.info(f"Master: {master_info}")
        logger.info(f"Slaves: {slaves_info}")
        logger.info("✓ Sentinel 정보 확인 테스트 성공")


class TestRedisPubSub:
    """Redis Pub/Sub 테스트"""
    
    @pytest.fixture
    def redis_conn(self):
        """Redis 연결 픽스처"""
        conn = RedisConnection()
        yield conn
        conn.close()
    
    @pytest.fixture
    def pubsub(self, redis_conn):
        """PubSub 픽스처"""
        ps = RedisPubSub(redis_conn)
        yield ps
        ps.stop_listening()
    
    def test_pubsub_basic(self, pubsub):
        """기본 Pub/Sub 테스트"""
        channel = 'test_channel'
        message = 'Hello Redis!'
        
        # 구독
        pubsub.subscribe(channel)
        
        # 메시지 수신 시작
        pubsub.listen()
        time.sleep(0.5)  # 구독 확인 대기
        
        # 메시지 발행
        result = pubsub.publish(channel, message)
        assert result >= 1  # 최소 1명의 구독자
        
        # 메시지 수신 확인
        time.sleep(0.5)
        messages = pubsub.get_messages()
        
        assert len(messages) > 0
        assert messages[0]['data'] == message
        assert messages[0]['channel'] == channel
        
        logger.info("✓ 기본 Pub/Sub 테스트 성공")
    
    def test_pubsub_multiple_channels(self, pubsub):
        """다중 채널 Pub/Sub 테스트"""
        channels = ['channel1', 'channel2', 'channel3']
        messages = ['message1', 'message2', 'message3']
        
        # 다중 채널 구독
        pubsub.subscribe(*channels)
        
        # 메시지 수신 시작
        pubsub.listen()
        time.sleep(0.5)
        
        # 각 채널에 메시지 발행
        for channel, message in zip(channels, messages):
            pubsub.publish(channel, message)
            time.sleep(0.1)
        
        # 메시지 수신 확인
        time.sleep(1)
        received_messages = pubsub.get_messages()
        
        assert len(received_messages) == 3
        
        # 각 메시지 확인
        for i, msg in enumerate(received_messages):
            assert msg['data'] == messages[i]
            assert msg['channel'] == channels[i]
        
        logger.info("✓ 다중 채널 Pub/Sub 테스트 성공")
    
    def test_pubsub_pattern_subscribe(self, pubsub):
        """패턴 구독 테스트"""
        pattern = 'news.*'
        channels = ['news.sports', 'news.tech', 'news.politics']
        message = 'Breaking news!'
        
        # 패턴 구독
        pubsub.psubscribe(pattern)
        
        # 메시지 수신 시작
        pubsub.listen()
        time.sleep(0.5)
        
        # 패턴과 일치하는 채널에 메시지 발행
        for channel in channels:
            pubsub.publish(channel, message)
            time.sleep(0.1)
        
        # 메시지 수신 확인
        time.sleep(1)
        received_messages = pubsub.get_messages()
        
        # 패턴 구독 메시지는 type이 'pmessage'
        pmessages = [msg for msg in received_messages if msg.get('type') == 'pmessage']
        assert len(pmessages) == 3
        
        for msg in pmessages:
            assert msg['data'] == message
            assert msg['pattern'] == pattern
        
        logger.info("✓ 패턴 구독 테스트 성공")


# ==================== 메인 실행 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("Redis Sentinel 연결 및 Pub/Sub 테스트")
    print("=" * 60)
    
    try:
        # Redis 연결 테스트
        print("\n[1] Redis 연결 테스트")
        conn = RedisConnection()
        master = conn.get_master()
        slave = conn.get_slave()
        
        print(f"✓ Master ping: {master.ping()}")
        print(f"✓ Slave ping: {slave.ping()}")
        print(f"✓ Master 정보: {conn.get_master_info()}")
        print(f"✓ Slaves 정보: {conn.get_slaves_info()}")
        
        # 기본 데이터 테스트
        print("\n[2] 기본 데이터 조작 테스트")
        master.set('test', 'hello', ex=60)
        time.sleep(0.1)
        print(f"✓ SET test = 'hello'")
        print(f"✓ GET test = '{slave.get('test')}'")
        
        # Hash 테스트
        master.hset('user:1000', mapping={'name': '홍길동', 'age': '30', 'city': '서울'})
        time.sleep(0.1)
        user_data = slave.hgetall('user:1000')
        print(f"✓ HGETALL user:1000 = {user_data}")
        
        # List 테스트
        master.lpush('tasks', 'task1', 'task2', 'task3')
        time.sleep(0.1)
        tasks = slave.lrange('tasks', 0, -1)
        print(f"✓ LRANGE tasks = {tasks}")
        
        # Pub/Sub 테스트
        print("\n[3] Pub/Sub 테스트")
        pubsub = RedisPubSub(conn)
        
        # 단일 채널 테스트
        pubsub.subscribe('notifications')
        pubsub.listen()
        time.sleep(0.5)
        
        result = pubsub.publish('notifications', '새로운 알림이 도착했습니다!')
        print(f"✓ PUBLISH notifications: {result}명 구독 중")
        
        time.sleep(0.5)
        messages = pubsub.get_messages()
        print(f"✓ 수신된 메시지: {len(messages)}개")
        for msg in messages:
            print(f"  - [{msg['channel']}] {msg['data']}")
        
        # 패턴 구독 테스트
        print("\n[4] 패턴 구독 테스트")
        pubsub.clear_messages()
        pubsub.psubscribe('log.*')
        time.sleep(0.5)
        
        pubsub.publish('log.info', 'INFO 로그 메시지')
        pubsub.publish('log.error', 'ERROR 로그 메시지')
        pubsub.publish('log.debug', 'DEBUG 로그 메시지')
        
        time.sleep(1)
        pattern_messages = pubsub.get_messages()
        print(f"✓ 패턴 메시지 수신: {len(pattern_messages)}개")
        for msg in pattern_messages:
            if msg['type'] == 'pmessage':
                print(f"  - [{msg['pattern']}] {msg['channel']}: {msg['data']}")
        
        # 정리
        print("\n[5] 정리")
        master.delete('test', 'user:1000', 'tasks')
        pubsub.stop_listening()
        conn.close()
        
        print("\n" + "=" * 60)
        print("✓ 모든 테스트 완료!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
