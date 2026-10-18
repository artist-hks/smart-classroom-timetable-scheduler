"""faculty, resources, time slots & breaks tables (SB2/US4/T1, US5/T1, US6/T1)

Revision ID: b7e2c4a91d05
Revises: 9fa0565135f6
Create Date: 2026-10-18 16:30:00.000000

Also adds the two deferred FK constraints that SB2/US2/T2 left open:
  sessions.resource_id       -> resources.resource_id
  session_faculty.faculty_id -> faculty.faculty_id
NOTE: if a database already holds sessions/session_faculty rows pointing at
ids that don't exist yet, those two FK creations will fail — clean such rows first.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b7e2c4a91d05'
down_revision: Union[str, Sequence[str], None] = '9fa0565135f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- faculty (US4) ------------------------------------------------------
    op.create_table(
        'faculty',
        sa.Column('faculty_id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('employee_code', sa.String(length=30), nullable=False),
        sa.Column('full_name', sa.String(length=150), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('designation', sa.String(length=100), nullable=True),
        sa.Column('max_weekly_hours', sa.Numeric(4, 1), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('max_weekly_hours > 0', name='ck_faculty_max_hours_positive'),
        sa.ForeignKeyConstraint(['department_id'], ['departments.department_id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('faculty_id'),
        sa.UniqueConstraint('employee_code', name='uq_faculty_employee_code'),
        sa.UniqueConstraint('email', name='uq_faculty_email'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index('ix_faculty_department_id', 'faculty', ['department_id'])

    op.create_table(
        'faculty_subjects',
        sa.Column('faculty_subject_id', sa.Integer(), nullable=False),
        sa.Column('faculty_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['faculty_id'], ['faculty.faculty_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['course_id'], ['courses.course_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('faculty_subject_id'),
        sa.UniqueConstraint('faculty_id', 'course_id', name='uq_faculty_subjects_pair'),
    )
    op.create_index('ix_faculty_subjects_course_id', 'faculty_subjects', ['course_id'])

    op.create_table(
        'faculty_availability',
        sa.Column('availability_id', sa.Integer(), nullable=False),
        sa.Column('faculty_id', sa.Integer(), nullable=False),
        sa.Column('day_of_week', sa.SmallInteger(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.CheckConstraint('day_of_week BETWEEN 1 AND 7', name='ck_faculty_availability_day_range'),
        sa.CheckConstraint('end_time > start_time', name='ck_faculty_availability_time_order'),
        sa.ForeignKeyConstraint(['faculty_id'], ['faculty.faculty_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('availability_id'),
    )
    op.create_index('ix_faculty_availability_faculty_day', 'faculty_availability', ['faculty_id', 'day_of_week'])

    # --- resources (US5) ----------------------------------------------------
    # resource_type_enum already exists (SB2/US2/T2) -> create_type=False.
    resource_type = postgresql.ENUM(
        'CLASSROOM', 'LABORATORY', 'SEMINAR_HALL', 'AUDITORIUM',
        name='resource_type_enum', create_type=False,
    )
    op.create_table(
        'resources',
        sa.Column('resource_id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('resource_type', resource_type, nullable=False),
        sa.Column('capacity', sa.Integer(), nullable=False),
        sa.Column('building', sa.String(length=100), nullable=True),
        sa.Column('floor', sa.SmallInteger(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('capacity > 0', name='ck_resources_capacity_positive'),
        sa.ForeignKeyConstraint(['department_id'], ['departments.department_id']),
        sa.PrimaryKeyConstraint('resource_id'),
        sa.UniqueConstraint('code', name='uq_resources_code'),
    )
    op.create_index('ix_resources_department_id', 'resources', ['department_id'])
    op.create_index('ix_resources_type', 'resources', ['resource_type'])

    op.create_table(
        'resource_equipment',
        sa.Column('equipment_id', sa.Integer(), nullable=False),
        sa.Column('resource_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('quantity', sa.Integer(), server_default='1', nullable=False),
        sa.CheckConstraint('quantity > 0', name='ck_resource_equipment_qty_positive'),
        sa.ForeignKeyConstraint(['resource_id'], ['resources.resource_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('equipment_id'),
        sa.UniqueConstraint('resource_id', 'name', name='uq_resource_equipment_name'),
    )

    # --- time slots & breaks (US6) -----------------------------------------
    op.create_table(
        'time_slots',
        sa.Column('time_slot_id', sa.Integer(), nullable=False),
        sa.Column('day_of_week', sa.SmallInteger(), nullable=False),
        sa.Column('period', sa.SmallInteger(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('label', sa.String(length=50), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.CheckConstraint('day_of_week BETWEEN 1 AND 7', name='ck_time_slots_day_range'),
        sa.CheckConstraint('period >= 1', name='ck_time_slots_period_positive'),
        sa.CheckConstraint('end_time > start_time', name='ck_time_slots_time_order'),
        sa.PrimaryKeyConstraint('time_slot_id'),
        sa.UniqueConstraint('day_of_week', 'period', name='uq_time_slots_day_period'),
    )
    op.create_table(
        'breaks',
        sa.Column('break_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=50), nullable=False),
        sa.Column('day_of_week', sa.SmallInteger(), nullable=True),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.CheckConstraint('day_of_week IS NULL OR day_of_week BETWEEN 1 AND 7', name='ck_breaks_day_range'),
        sa.CheckConstraint('end_time > start_time', name='ck_breaks_time_order'),
        sa.PrimaryKeyConstraint('break_id'),
    )

    # --- deferred FKs from SB2/US2/T2 --------------------------------------
    op.create_foreign_key(
        'fk_sessions_resource_id', 'sessions', 'resources', ['resource_id'], ['resource_id']
    )
    op.create_foreign_key(
        'fk_session_faculty_faculty_id', 'session_faculty', 'faculty', ['faculty_id'], ['faculty_id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_session_faculty_faculty_id', 'session_faculty', type_='foreignkey')
    op.drop_constraint('fk_sessions_resource_id', 'sessions', type_='foreignkey')
    op.drop_table('breaks')
    op.drop_table('time_slots')
    op.drop_table('resource_equipment')
    op.drop_index('ix_resources_type', table_name='resources')
    op.drop_index('ix_resources_department_id', table_name='resources')
    op.drop_table('resources')
    op.drop_index('ix_faculty_availability_faculty_day', table_name='faculty_availability')
    op.drop_table('faculty_availability')
    op.drop_index('ix_faculty_subjects_course_id', table_name='faculty_subjects')
    op.drop_table('faculty_subjects')
    op.drop_index('ix_faculty_department_id', table_name='faculty')
    op.drop_table('faculty')
    # resource_type_enum is still used by sessions / course_session_type_configs — do NOT drop it.
