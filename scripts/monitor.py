#!python
"""
스케줄러 작업 진행 상황 실시간 모니터링 스크립트

사용법:
  ./scripts/monitor.py collect     # 리뷰 수집 모니터링
  ./scripts/monitor.py analyze     # 리뷰 분석 모니터링
  ./scripts/monitor.py sync        # OpenSearch 동기화 모니터링
  ./scripts/monitor.py wordcloud   # 워드클라우드 생성 모니터링
  ./scripts/monitor.py all         # 전체 파이프라인 모니터링
"""

import sys
import os
import time
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.layout import Layout
from rich import box

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scheduler.utils.database import get_db_session
from sqlalchemy import text
from app.core.opensearch_client import get_opensearch_client


def get_collection_stats():
    """수집 통계 조회"""
    try:
        session = get_db_session()
        result = session.execute(text("SELECT COUNT(*) as count FROM reviews"))
        total = result.fetchone()[0]
        session.close()
        return {'total_reviews': total}
    except Exception as e:
        return {'error': str(e)}


def get_sync_stats():
    """동기화 통계 조회"""
    try:
        session = get_db_session()
        
        # MySQL 전체 리뷰
        result = session.execute(text("SELECT COUNT(*) as count FROM reviews"))
        total_reviews = result.fetchone()[0]
        
        # MySQL 동기화된 리뷰
        result = session.execute(text("SELECT COUNT(*) as count FROM reviews WHERE synced_to_opensearch = 1"))
        synced = result.fetchone()[0]
        
        session.close()
        
        # OpenSearch 문서 수
        os_client = get_opensearch_client()
        client = os_client.sync_client
        total_query = {"query": {"match_all": {}}}
        os_resp = client.count(index="app_reviews", body=total_query)
        os_docs = os_resp['count']
        
        unsynced = total_reviews - synced
        progress = (synced / total_reviews * 100) if total_reviews > 0 else 0
        
        return {
            'total_reviews': total_reviews,
            'synced': synced,
            'unsynced': unsynced,
            'os_docs': os_docs,
            'progress': progress
        }
    except Exception as e:
        return {'error': str(e)}


def get_analysis_stats():
    """분석 통계 조회 (MariaDB 기준)"""
    try:
        with get_db_session() as session:
            # 전체 리뷰
            total = session.execute(text("SELECT COUNT(*) FROM reviews")).scalar()
            
            # 분석 완료
            analyzed = session.execute(text("SELECT COUNT(*) FROM reviews WHERE analyzed = 1")).scalar()
            
            unanalyzed = total - analyzed
            progress = (analyzed / total * 100) if total > 0 else 0
            
            return {
                'total': total,
                'analyzed': analyzed,
                'unanalyzed': unanalyzed,
                'progress': progress
            }
    except Exception as e:
        return {'error': str(e)}


def get_wordcloud_stats():
    """워드클라우드 통계 조회"""
    try:
        wordcloud_dir = Path("/var/data/wordclouds")
        
        if not wordcloud_dir.exists():
            return {'total_files': 0, 'latest': None, 'latest_time': None}
        
        files = list(wordcloud_dir.glob("*.png"))
        
        if files:
            latest = max(files, key=lambda f: f.stat().st_mtime)
            latest_time = datetime.fromtimestamp(latest.stat().st_mtime)
        else:
            latest = None
            latest_time = None
        
        return {
            'total_files': len(files),
            'latest': latest.name if latest else None,
            'latest_time': latest_time
        }
    except Exception as e:
        return {'error': str(e)}


def progress_bar(progress, length=40):
    """진행률 바 생성"""
    filled = int(length * progress / 100)
    return '█' * filled + '░' * (length - filled)


def monitor_collection(interval=30):
    """수집 모니터링"""
    print("📥 리뷰 수집 모니터링 (Ctrl+C로 종료)\n")
    
    prev_total = None
    
    try:
        while True:
            stats = get_collection_stats()
            now = datetime.now().strftime('%H:%M:%S')
            
            if 'error' in stats:
                print(f"\r[{now}] ❌ 조회 실패: {stats['error']}", end='', flush=True)
            else:
                speed = ""
                if prev_total is not None:
                    diff = stats['total_reviews'] - prev_total
                    if diff > 0:
                        speed = f" (+{diff} in {interval}s, ~{diff*60//interval}/min)"
                
                print(f"\r[{now}] 수집된 리뷰: {stats['total_reviews']:,}{speed}", end='', flush=True)
                prev_total = stats['total_reviews']
            
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n\n모니터링 종료")


def monitor_sync(interval=30):
    """동기화 모니터링"""
    print("🔄 OpenSearch 동기화 모니터링 (Ctrl+C로 종료)\n")
    
    prev_synced = None
    
    try:
        while True:
            stats = get_sync_stats()
            now = datetime.now().strftime('%H:%M:%S')
            
            if 'error' in stats:
                print(f"\r[{now}] ❌ 조회 실패: {stats['error']}", end='', flush=True)
            else:
                bar = progress_bar(stats['progress'])
                speed = ""
                if prev_synced is not None:
                    diff = stats['synced'] - prev_synced
                    if diff > 0:
                        speed = f" (+{diff} in {interval}s, ~{diff*60//interval}/min)"
                
                print(f"\r[{now}] {bar} {stats['progress']:.1f}% | "
                      f"동기화완료: {stats['synced']:,} | "
                      f"미동기화: {stats['unsynced']:,} | "
                      f"OS문서: {stats['os_docs']:,}{speed}", end='', flush=True)
                
                prev_synced = stats['synced']
            
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n\n모니터링 종료")


def monitor_analysis(interval=30):
    """분석 모니터링"""
    print("🧠 리뷰 분석 모니터링 (Ctrl+C로 종료)\n")
    
    prev_analyzed = None
    
    try:
        while True:
            stats = get_analysis_stats()
            now = datetime.now().strftime('%H:%M:%S')
            
            if 'error' in stats:
                print(f"\r[{now}] ❌ 조회 실패: {stats['error']}", end='', flush=True)
            else:
                bar = progress_bar(stats['progress'])
                speed = ""
                if prev_analyzed is not None:
                    diff = stats['analyzed'] - prev_analyzed
                    if diff > 0:
                        speed = f" (+{diff} in {interval}s, ~{diff*60//interval}/min)"
                
                print(f"\r[{now}] {bar} {stats['progress']:.1f}% | "
                      f"분석완료: {stats['analyzed']:,} | "
                      f"미분석: {stats['unanalyzed']:,}{speed}", end='', flush=True)
                
                prev_analyzed = stats['analyzed']
            
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n\n모니터링 종료")


def monitor_wordcloud(interval=30):
    """워드클라우드 모니터링"""
    print("☁️  워드클라우드 생성 모니터링 (Ctrl+C로 종료)\n")
    
    prev_total = None
    
    try:
        while True:
            stats = get_wordcloud_stats()
            now = datetime.now().strftime('%H:%M:%S')
            
            if 'error' in stats:
                print(f"\r[{now}] ❌ 조회 실패: {stats['error']}", end='', flush=True)
            else:
                speed = ""
                if prev_total is not None:
                    diff = stats['total_files'] - prev_total
                    if diff > 0:
                        speed = f" (+{diff} 신규)"
                
                latest_str = ""
                if stats['latest']:
                    latest_str = f" | 최근: {stats['latest']} ({stats['latest_time'].strftime('%H:%M:%S')})"
                
                print(f"\r[{now}] 생성된 파일: {stats['total_files']}{speed}{latest_str}", end='', flush=True)
                prev_total = stats['total_files']
            
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n\n모니터링 종료")


def generate_status_table():
    """현재 상태를 Rich 테이블로 생성"""
    table = Table(title="📊 전체 파이프라인 상태", box=box.ROUNDED, show_header=True, header_style="bold cyan")
    
    table.add_column("작업", style="cyan", width=12)
    table.add_column("진행률", justify="center", width=40)
    table.add_column("상세", justify="right", style="yellow")
    table.add_column("상태", justify="center", width=20)
    
    # 수집
    collect = get_collection_stats()
    if 'error' not in collect:
        table.add_row(
            "📥 수집",
            "완료",
            f"{collect['total_reviews']:,} 리뷰",
            "[green]●[/green] 정상"
        )
    
    # 동기화
    sync = get_sync_stats()
    if 'error' not in sync:
        bar = progress_bar(sync['progress'], 25)
        table.add_row(
            "🔄 동기화",
            f"{bar} {sync['progress']:.1f}%",
            f"{sync['synced']:,} / {sync['total_reviews']:,}",
            f"[yellow]●[/yellow] {sync['unsynced']:,} 대기"
        )
    
    # 분석
    analyze = get_analysis_stats()
    if 'error' not in analyze:
        bar = progress_bar(analyze['progress'], 25)

        # 배치 프로세스 실행 여부 확인
        import subprocess
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=2
            )
            # 실제 프로세스명: scheduler.main --run-once analyze
            is_running = "scheduler.main" in result.stdout and "analyze" in result.stdout
        except:
            is_running = False

        if analyze['progress'] >= 100:
            status_color = "green"
            status_text = "완료"
        elif is_running:
            status_color = "green"
            status_text = f"● 진행중 ({analyze['unanalyzed']:,} 대기)"
        else:
            status_color = "yellow"
            status_text = f"● {analyze['unanalyzed']:,} 대기"

        table.add_row(
            "🧠 분석",
            f"{bar} {analyze['progress']:.1f}%",
            f"{analyze['analyzed']:,} / {analyze['total']:,}",
            f"[{status_color}]{status_text}[/{status_color}]"
        )
    
    # 워드클라우드
    wc = get_wordcloud_stats()
    if 'error' not in wc:
        latest_time = wc.get('latest_time')
        latest = f"{latest_time.strftime('%m/%d %H:%M')}" if latest_time else "-"
        table.add_row(
            "☁️  WC",
            "-",
            f"{wc['total_files']} 파일",
            f"최근: {latest}"
        )
    
    return table


def monitor_all(interval=30):
    """전체 파이프라인 모니터링 (Rich 라이브러리 사용)"""
    console = Console()
    
    console.print("\n[bold green]📊 전체 파이프라인 실시간 모니터링[/bold green]")
    console.print(f"[dim]갱신 간격: {interval}초 | Ctrl+C로 종료[/dim]\n")
    
    try:
        with Live(generate_status_table(), refresh_per_second=1, console=console) as live:
            while True:
                time.sleep(interval)
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # 테이블 업데이트
                table = generate_status_table()
                table.caption = f"[dim]마지막 갱신: {now}[/dim]"
                live.update(table)
                
    except KeyboardInterrupt:
        console.print("\n[yellow]모니터링 종료[/yellow]")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    mode = sys.argv[1].lower()
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    
    monitors = {
        'collect': monitor_collection,
        'sync': monitor_sync,
        'analyze': monitor_analysis,
        'wordcloud': monitor_wordcloud,
        'all': monitor_all
    }
    
    if mode not in monitors:
        print(f"❌ 알 수 없는 모드: {mode}")
        print(__doc__)
        sys.exit(1)
    
    monitors[mode](interval)


if __name__ == "__main__":
    main()
