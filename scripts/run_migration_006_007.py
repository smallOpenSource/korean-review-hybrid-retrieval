#!/usr/bin/env python
"""
Migration 006 & 007 실행 스크립트.
complaint_dept → complaint_primary_dept 마이그레이션을 안전하게 실행합니다.

Usage:
    python scripts/run_migration_006_007.py [--dry-run] [--skip-006] [--skip-007]

Options:
    --dry-run: SQL 출력만 하고 실제 실행하지 않음
    --skip-006: Migration 006 건너뛰기
    --skip-007: Migration 007 건너뛰기
"""
import sys
import os
import argparse
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.mysql_client import get_mysql_client


def print_header(title):
    """Print section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def read_migration_file(filename):
    """Read migration SQL file."""
    filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'migrations', filename)

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Migration file not found: {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def extract_sql_statements(content):
    """Extract executable SQL statements from migration file."""
    lines = []
    for line in content.split('\n'):
        # Skip comments and empty lines
        stripped = line.strip()
        if not stripped or stripped.startswith('--'):
            continue
        lines.append(line)

    full_sql = '\n'.join(lines)

    # Split by semicolon but keep it simple (not perfect for all cases)
    statements = []
    current = []

    for line in full_sql.split('\n'):
        current.append(line)
        if line.rstrip().endswith(';'):
            stmt = '\n'.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []

    return statements


def execute_migration(mysql, statements, dry_run=False):
    """Execute migration statements."""
    if dry_run:
        print("\n[DRY RUN MODE - SQL 출력만 수행]\n")
        for i, stmt in enumerate(statements, 1):
            print(f"-- Statement {i}:")
            print(stmt)
            print()
        return True, len(statements), 0

    success_count = 0
    failed_count = 0

    for i, stmt in enumerate(statements, 1):
        try:
            print(f"\n실행 중 ({i}/{len(statements)}): ", end='')
            # Show first 50 chars of statement
            preview = stmt.replace('\n', ' ')[:50]
            print(f"{preview}...")

            mysql.execute(stmt)
            print("  ✅ 성공")
            success_count += 1

        except Exception as e:
            print(f"  ❌ 실패: {e}")
            failed_count += 1

            # Ask whether to continue
            response = input("\n계속 진행하시겠습니까? (y/N): ")
            if response.lower() != 'y':
                print("마이그레이션 중단됨")
                return False, success_count, failed_count

    return True, success_count, failed_count


def run_migration_006(dry_run=False):
    """Run migration 006."""
    print_header("Migration 006: Fix Complaint Field Naming")

    print("\n이 마이그레이션은 다음을 수행합니다:")
    print("  1. complaint_dept → complaint_primary_dept (컬럼명 변경)")
    print("  2. 신규 컬럼 3개 추가 (sla_deadline, assigned_to, escalated_to)")
    print("  3. 인덱스 2개 추가")
    print("  4. 기존 데이터 마이그레이션 (escalated_to, sla_deadline)")
    print()

    if not dry_run:
        response = input("진행하시겠습니까? (y/N): ")
        if response.lower() != 'y':
            print("❌ Migration 006 건너뜀")
            return False

    try:
        content = read_migration_file('006_fix_complaint_fields.sql')
        statements = extract_sql_statements(content)

        print(f"\n총 {len(statements)}개 SQL 문장 발견")

        mysql = get_mysql_client()
        success, ok_count, fail_count = execute_migration(mysql, statements, dry_run)

        if success:
            print(f"\n✅ Migration 006 완료 (성공: {ok_count}, 실패: {fail_count})")
            return True
        else:
            print(f"\n❌ Migration 006 실패 (성공: {ok_count}, 실패: {fail_count})")
            return False

    except Exception as e:
        print(f"\n❌ Migration 006 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_migration_007(dry_run=False):
    """Run migration 007."""
    print_header("Migration 007: Add Composite Indexes")

    print("\n이 마이그레이션은 다음을 수행합니다:")
    print("  - 7개 복합 인덱스 추가 (성능 최적화)")
    print("    1. idx_sync_pipeline")
    print("    2. idx_complaint_dept_status")
    print("    3. idx_complaint_sla")
    print("    4. idx_app_timeline")
    print("    5. idx_complaint_timeline")
    print("    6. idx_year_month_complaint")
    print("    7. idx_complaint_urgency_time")
    print()

    if not dry_run:
        response = input("진행하시겠습니까? (y/N): ")
        if response.lower() != 'y':
            print("❌ Migration 007 건너뜀")
            return False

    try:
        content = read_migration_file('007_add_composite_indexes.sql')
        statements = extract_sql_statements(content)

        print(f"\n총 {len(statements)}개 SQL 문장 발견")

        mysql = get_mysql_client()
        success, ok_count, fail_count = execute_migration(mysql, statements, dry_run)

        if success:
            print(f"\n✅ Migration 007 완료 (성공: {ok_count}, 실패: {fail_count})")
            return True
        else:
            print(f"\n❌ Migration 007 실패 (성공: {ok_count}, 실패: {fail_count})")
            return False

    except Exception as e:
        print(f"\n❌ Migration 007 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_migration():
    """Verify migration results."""
    print_header("마이그레이션 검증")

    try:
        mysql = get_mysql_client()

        # Check new column exists
        result = mysql.execute_one("""
            SELECT COUNT(*) as cnt
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'reviews'
            AND column_name = 'complaint_primary_dept'
        """)

        if result and result['cnt'] > 0:
            print("✅ complaint_primary_dept 컬럼 생성 확인")
        else:
            print("❌ complaint_primary_dept 컬럼 없음")
            return False

        # Check data migration
        result = mysql.execute_one("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN complaint_escalated_to IS NOT NULL THEN 1 ELSE 0 END) as with_escalation,
                SUM(CASE WHEN complaint_sla_deadline IS NOT NULL THEN 1 ELSE 0 END) as with_sla
            FROM reviews
            WHERE is_complaint = 1
        """)

        if result:
            print(f"✅ 민원 데이터: {result['total']:,}개")
            print(f"   - escalated_to 설정: {result['with_escalation']:,}개")
            print(f"   - sla_deadline 설정: {result['with_sla']:,}개")

        # Check indexes
        result = mysql.execute_all("""
            SELECT index_name
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
            AND table_name = 'reviews'
            AND index_name IN (
                'idx_sync_pipeline',
                'idx_complaint_dept_status',
                'idx_complaint_sla',
                'idx_app_timeline',
                'idx_complaint_timeline',
                'idx_year_month_complaint',
                'idx_complaint_urgency_time'
            )
            GROUP BY index_name
        """)

        print(f"\n✅ 복합 인덱스: {len(result)}/7개 생성됨")
        for row in result:
            print(f"   - {row['index_name']}")

        return True

    except Exception as e:
        print(f"❌ 검증 실패: {e}")
        return False


def main():
    """Main execution flow."""
    parser = argparse.ArgumentParser(description='Run migrations 006 & 007')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode (no actual execution)')
    parser.add_argument('--skip-006', action='store_true', help='Skip migration 006')
    parser.add_argument('--skip-007', action='store_true', help='Skip migration 007')

    args = parser.parse_args()

    print("\n")
    print("╔════════════════════════════════════════════════════════════════════════════╗")
    print("║              Migration 006 & 007 실행 스크립트                             ║")
    print("║              complaint_dept → complaint_primary_dept                      ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝")

    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - 실제 실행하지 않고 SQL만 출력합니다\n")

    results = {}

    # Run migration 006
    if not args.skip_006:
        results['006'] = run_migration_006(args.dry_run)
    else:
        print("\n⚠️  Migration 006 건너뜀 (--skip-006)")
        results['006'] = None

    # Run migration 007
    if not args.skip_007:
        results['007'] = run_migration_007(args.dry_run)
    else:
        print("\n⚠️  Migration 007 건너뜀 (--skip-007)")
        results['007'] = None

    # Verify
    if not args.dry_run and any(results.values()):
        verify_success = verify_migration()
    else:
        verify_success = None

    # Summary
    print_header("실행 결과 요약")

    if args.dry_run:
        print("\n✅ DRY RUN 완료 - 실제 변경 없음")
        return 0

    for migration, success in results.items():
        if success is None:
            print(f"⚠️  Migration {migration}: 건너뜀")
        elif success:
            print(f"✅ Migration {migration}: 성공")
        else:
            print(f"❌ Migration {migration}: 실패")

    if verify_success:
        print("\n✅ 검증 완료")
    elif verify_success is False:
        print("\n❌ 검증 실패")

    print("\n다음 단계:")
    print("  1. OpenSearch 재인덱싱: python scripts/reindex_complaints.py")
    print("  2. Scheduler 재시작: systemctl restart appreviews-scheduler")

    if all(v for v in results.values() if v is not None):
        return 0
    else:
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
