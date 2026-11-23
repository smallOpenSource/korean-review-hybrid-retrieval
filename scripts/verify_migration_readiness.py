#!/usr/bin/env python
"""
마이그레이션 006, 007 실행 전 사전 검증 스크립트.
데이터베이스 상태를 확인하고 마이그레이션 가능 여부를 판단합니다.

Usage:
    python scripts/verify_migration_readiness.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.mysql_client import get_mysql_client
import pymysql


def print_header(title):
    """Print section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_check(name, passed, detail=""):
    """Print check result."""
    icon = "✅" if passed else "❌"
    status = "PASS" if passed else "FAIL"
    print(f"{icon} [{status}] {name}")
    if detail:
        print(f"         → {detail}")
    return passed


def verify_mysql_connection():
    """MySQL 연결 확인."""
    print_header("Step 1: MySQL 연결 확인")

    try:
        mysql = get_mysql_client()
        result = mysql.execute_one("SELECT VERSION() as version")
        version = result['version'] if result else "Unknown"
        return print_check("MySQL 연결", True, f"Version: {version}")
    except Exception as e:
        return print_check("MySQL 연결", False, str(e))


def verify_table_exists():
    """reviews 테이블 존재 확인."""
    print_header("Step 2: reviews 테이블 확인")

    try:
        mysql = get_mysql_client()
        result = mysql.execute_one("""
            SELECT COUNT(*) as cnt
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'reviews'
        """)
        exists = result['cnt'] > 0 if result else False

        if exists:
            count_result = mysql.execute_one("SELECT COUNT(*) as total FROM reviews")
            total = count_result['total'] if count_result else 0
            return print_check("reviews 테이블 존재", True, f"총 {total:,}개 레코드")
        else:
            return print_check("reviews 테이블 존재", False, "테이블 없음")
    except Exception as e:
        return print_check("reviews 테이블 확인", False, str(e))


def verify_old_column_exists():
    """complaint_dept 컬럼 존재 확인."""
    print_header("Step 3: 기존 컬럼 확인")

    try:
        mysql = get_mysql_client()
        result = mysql.execute_one("""
            SELECT COUNT(*) as cnt
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'reviews'
            AND column_name = 'complaint_dept'
        """)
        exists = result['cnt'] > 0 if result else False

        if exists:
            # 데이터 개수 확인
            data_result = mysql.execute_one("""
                SELECT COUNT(*) as cnt
                FROM reviews
                WHERE complaint_dept IS NOT NULL
            """)
            data_count = data_result['cnt'] if data_result else 0
            return print_check("complaint_dept 컬럼 존재", True,
                             f"데이터 {data_count:,}개 (마이그레이션 필요)")
        else:
            return print_check("complaint_dept 컬럼 존재", False,
                             "이미 마이그레이션 완료되었거나 컬럼이 없음")
    except Exception as e:
        return print_check("기존 컬럼 확인", False, str(e))


def verify_new_columns_not_exist():
    """신규 컬럼이 아직 없는지 확인."""
    print_header("Step 4: 신규 컬럼 중복 확인")

    new_columns = ['complaint_primary_dept', 'complaint_sla_deadline',
                   'complaint_assigned_to', 'complaint_escalated_to']

    all_clear = True
    try:
        mysql = get_mysql_client()

        for col in new_columns:
            result = mysql.execute_one(f"""
                SELECT COUNT(*) as cnt
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                AND table_name = 'reviews'
                AND column_name = '{col}'
            """)
            exists = result['cnt'] > 0 if result else False

            if exists:
                all_clear = False
                print_check(f"{col} 미존재", False, "이미 존재함 (중복 마이그레이션 위험)")
            else:
                print_check(f"{col} 미존재", True, "생성 가능")

        return all_clear
    except Exception as e:
        return print_check("신규 컬럼 확인", False, str(e))


def verify_indexes():
    """기존 인덱스 확인."""
    print_header("Step 5: 인덱스 현황")

    try:
        mysql = get_mysql_client()
        result = mysql.execute_all("""
            SELECT DISTINCT index_name, cardinality
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
            AND table_name = 'reviews'
            AND index_name LIKE 'idx_complaint%'
            ORDER BY index_name
        """)

        if result:
            print("  기존 complaint 관련 인덱스:")
            for row in result:
                print(f"    - {row['index_name']} (cardinality: {row['cardinality']})")
            return print_check("인덱스 조회", True, f"{len(result)}개 발견")
        else:
            return print_check("인덱스 조회", True, "complaint 관련 인덱스 없음")
    except Exception as e:
        return print_check("인덱스 확인", False, str(e))


def verify_disk_space():
    """디스크 공간 확인."""
    print_header("Step 6: 디스크 공간")

    try:
        mysql = get_mysql_client()
        result = mysql.execute_one("""
            SELECT
                table_name,
                ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'reviews'
        """)

        if result:
            size_mb = result['size_mb']
            # 마이그레이션에 필요한 여유 공간 (인덱스 추가 등 고려)
            required_mb = size_mb * 0.3  # 30% 여유 필요

            return print_check("테이블 크기 확인", True,
                             f"현재: {size_mb:.2f} MB, 예상 필요 공간: {required_mb:.2f} MB")
        else:
            return print_check("디스크 공간 확인", False, "테이블 크기 조회 실패")
    except Exception as e:
        return print_check("디스크 공간 확인", False, str(e))


def verify_active_connections():
    """활성 연결 확인 (마이그레이션 중 잠금 가능성)."""
    print_header("Step 7: 활성 연결 확인")

    try:
        mysql = get_mysql_client()
        result = mysql.execute_one("""
            SELECT COUNT(*) as cnt
            FROM information_schema.processlist
            WHERE db = DATABASE()
            AND command != 'Sleep'
        """)

        active_count = result['cnt'] if result else 0

        if active_count > 10:
            return print_check("활성 연결 수", False,
                             f"{active_count}개 (너무 많음, 마이그레이션 중 대기 시간 증가 가능)")
        else:
            return print_check("활성 연결 수", True, f"{active_count}개 (정상)")
    except Exception as e:
        return print_check("활성 연결 확인", False, str(e))


def verify_backup_exists():
    """백업 권장 사항."""
    print_header("Step 8: 백업 권장")

    print("⚠️  마이그레이션 전 반드시 백업을 수행하세요:")
    print("    mysqldump -u $MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DATABASE \\")
    print("      > backup_before_migration_$(date +%Y%m%d_%H%M%S).sql")
    print()

    response = input("백업을 완료했습니까? (y/N): ")
    return print_check("백업 완료", response.lower() == 'y',
                      "백업 완료" if response.lower() == 'y' else "백업 필요")


def main():
    """Main verification flow."""
    print("\n")
    print("╔════════════════════════════════════════════════════════════════════════════╗")
    print("║         Migration 006 & 007 사전 검증 스크립트                             ║")
    print("║         complaint_dept → complaint_primary_dept 마이그레이션               ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝")

    checks = []

    # Run all checks
    checks.append(verify_mysql_connection())
    checks.append(verify_table_exists())
    checks.append(verify_old_column_exists())
    checks.append(verify_new_columns_not_exist())
    checks.append(verify_indexes())
    checks.append(verify_disk_space())
    checks.append(verify_active_connections())
    checks.append(verify_backup_exists())

    # Summary
    print_header("검증 결과 요약")

    passed = sum(checks)
    total = len(checks)

    print(f"\n총 {total}개 검증 중 {passed}개 통과")
    print()

    if passed == total:
        print("✅ 모든 검증 통과! 마이그레이션을 진행해도 됩니다.")
        print()
        print("다음 명령어를 실행하세요:")
        print("  python scripts/run_migration.py")
        return 0
    else:
        print(f"❌ {total - passed}개 검증 실패. 문제를 해결한 후 다시 시도하세요.")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  사용자에 의해 중단됨")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
