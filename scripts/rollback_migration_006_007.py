#!/usr/bin/env python
"""
Migration 006 & 007 롤백 스크립트.
문제 발생 시 이전 상태로 복구합니다.

Usage:
    python scripts/rollback_migration_006_007.py [--dry-run] [--rollback-006] [--rollback-007]

Options:
    --dry-run: SQL 출력만 하고 실제 실행하지 않음
    --rollback-006: Migration 006만 롤백
    --rollback-007: Migration 007만 롤백
"""
import os
import sys
import argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.mysql_client import get_mysql_client


def print_header(title):
    """Print section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def rollback_migration_007(dry_run=False):
    """Rollback migration 007 (복합 인덱스 제거)."""
    print_header("Rollback Migration 007: Drop Composite Indexes")

    statements = [
        "ALTER TABLE reviews DROP INDEX idx_sync_pipeline",
        "ALTER TABLE reviews DROP INDEX idx_complaint_dept_status",
        "ALTER TABLE reviews DROP INDEX idx_complaint_sla",
        "ALTER TABLE reviews DROP INDEX idx_app_timeline",
        "ALTER TABLE reviews DROP INDEX idx_complaint_timeline",
        "ALTER TABLE reviews DROP INDEX idx_year_month_complaint",
        "ALTER TABLE reviews DROP INDEX idx_complaint_urgency_time"
    ]

    print(f"\n제거할 인덱스: {len(statements)}개")

    if not dry_run:
        response = input("진행하시겠습니까? (y/N): ")
        if response.lower() != 'y':
            print("❌ Rollback 007 건너뜀")
            return False

    if dry_run:
        print("\n[DRY RUN MODE]\n")
        for stmt in statements:
            print(stmt + ";")
        return True

    mysql = get_mysql_client()
    success_count = 0
    failed_count = 0

    for stmt in statements:
        try:
            mysql.execute(stmt)
            print(f"✅ {stmt.split('DROP INDEX ')[1]}")
            success_count += 1
        except Exception as e:
            print(f"❌ 실패: {e}")
            failed_count += 1

    print(f"\n✅ Rollback 007 완료 (성공: {success_count}, 실패: {failed_count})")
    return True


def rollback_migration_006(dry_run=False):
    """Rollback migration 006 (컬럼명 및 신규 컬럼 제거)."""
    print_header("Rollback Migration 006: Revert Complaint Field Changes")

    print("\n⚠️  WARNING: 이 작업은 다음 데이터를 손실합니다:")
    print("  - complaint_sla_deadline 데이터")
    print("  - complaint_assigned_to 데이터")
    print("  - complaint_escalated_to 데이터")
    print()

    statements = [
        # 신규 컬럼 제거 전 인덱스 제거
        "ALTER TABLE reviews DROP INDEX idx_complaint_assigned_to",
        "ALTER TABLE reviews DROP INDEX idx_complaint_sla_deadline",
        # 컬럼명 복원
        "ALTER TABLE reviews CHANGE COLUMN complaint_primary_dept complaint_dept VARCHAR(50)",
        # 신규 컬럼 제거
        "ALTER TABLE reviews DROP COLUMN complaint_sla_deadline",
        "ALTER TABLE reviews DROP COLUMN complaint_assigned_to",
        "ALTER TABLE reviews DROP COLUMN complaint_escalated_to"
    ]

    if not dry_run:
        response = input("정말 진행하시겠습니까? 데이터가 손실됩니다! (yes/N): ")
        if response != 'yes':
            print("❌ Rollback 006 취소됨")
            return False

    if dry_run:
        print("\n[DRY RUN MODE]\n")
        for stmt in statements:
            print(stmt + ";")
        return True

    mysql = get_mysql_client()
    success_count = 0
    failed_count = 0

    for stmt in statements:
        try:
            print(f"\n실행 중: {stmt[:60]}...")
            mysql.execute(stmt)
            print("  ✅ 성공")
            success_count += 1
        except Exception as e:
            print(f"  ❌ 실패: {e}")
            failed_count += 1

            response = input("\n계속 진행하시겠습니까? (y/N): ")
            if response.lower() != 'y':
                print("Rollback 중단됨")
                return False

    print(f"\n✅ Rollback 006 완료 (성공: {success_count}, 실패: {failed_count})")
    return True


def verify_rollback():
    """Verify rollback results."""
    print_header("롤백 검증")

    try:
        mysql = get_mysql_client()

        # Check old column restored
        result = mysql.execute_one("""
            SELECT COUNT(*) as cnt
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'reviews'
            AND column_name = 'complaint_dept'
        """)

        if result and result['cnt'] > 0:
            print("✅ complaint_dept 컬럼 복원 확인")
        else:
            print("⚠️  complaint_dept 컬럼 없음 (rollback 006 미실행)")

        # Check new columns removed
        new_cols = ['complaint_primary_dept', 'complaint_sla_deadline',
                   'complaint_assigned_to', 'complaint_escalated_to']

        for col in new_cols:
            result = mysql.execute_one(f"""
                SELECT COUNT(*) as cnt
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                AND table_name = 'reviews'
                AND column_name = '{col}'
            """)

            if result and result['cnt'] == 0:
                print(f"✅ {col} 제거 확인")
            else:
                print(f"⚠️  {col} 아직 존재")

        # Check indexes removed
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

        if len(result) == 0:
            print("\n✅ 모든 복합 인덱스 제거 확인")
        else:
            print(f"\n⚠️  {len(result)}개 인덱스 남아있음:")
            for row in result:
                print(f"   - {row['index_name']}")

        return True

    except Exception as e:
        print(f"❌ 검증 실패: {e}")
        return False


def main():
    """Main execution flow."""
    parser = argparse.ArgumentParser(description='Rollback migrations 006 & 007')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    parser.add_argument('--rollback-006', action='store_true', help='Rollback migration 006 only')
    parser.add_argument('--rollback-007', action='store_true', help='Rollback migration 007 only')

    args = parser.parse_args()

    print("\n")
    print("╔════════════════════════════════════════════════════════════════════════════╗")
    print("║           Migration 006 & 007 롤백 스크립트                                ║")
    print("║           ⚠️  WARNING: 데이터 손실 가능                                    ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝")

    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - 실제 실행하지 않고 SQL만 출력합니다\n")

    # Determine what to rollback
    if not args.rollback_006 and not args.rollback_007:
        # Default: rollback both (in reverse order)
        rollback_both = True
    else:
        rollback_both = False

    results = {}

    # Rollback in reverse order (007 first, then 006)
    if rollback_both or args.rollback_007:
        results['007'] = rollback_migration_007(args.dry_run)

    if rollback_both or args.rollback_006:
        results['006'] = rollback_migration_006(args.dry_run)

    # Verify
    if not args.dry_run and any(results.values()):
        verify_rollback()

    # Summary
    print_header("롤백 결과 요약")

    if args.dry_run:
        print("\n✅ DRY RUN 완료 - 실제 변경 없음")
        return 0

    for migration, success in results.items():
        if success:
            print(f"✅ Migration {migration} 롤백: 성공")
        else:
            print(f"❌ Migration {migration} 롤백: 실패")

    print("\n⚠️  롤백 후 필요한 작업:")
    print("  1. 코드를 이전 버전으로 복원")
    print("  2. Scheduler 재시작")
    print("  3. OpenSearch 데이터 확인")

    if all(results.values()):
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
