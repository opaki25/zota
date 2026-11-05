"""Discovery evidence, outreach history, and recipient suppression."""
from alembic import op
import sqlalchemy as sa
revision = '0002'
down_revision = '0001'

def upgrade():
    op.create_table('prospects',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('place_id',sa.String(300),nullable=False,unique=True),sa.Column('name',sa.String(200),nullable=False),
        sa.Column('city',sa.String(200),nullable=False),sa.Column('industry',sa.String(100),nullable=False),
        sa.Column('evidence',sa.Text(),nullable=False),sa.Column('state',sa.String(40),nullable=False),
        sa.Column('business_id',sa.String(36),sa.ForeignKey('businesses.id',ondelete='SET NULL'),nullable=True))
    op.create_table('outreach',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('business_id',sa.String(36),sa.ForeignKey('businesses.id',ondelete='SET NULL'),nullable=True),
        sa.Column('channel',sa.String(20),nullable=False),sa.Column('recipient',sa.String(320),nullable=False),
        sa.Column('subject',sa.String(200),nullable=False),sa.Column('body',sa.Text(),nullable=False),
        sa.Column('state',sa.String(30),nullable=False),sa.Column('provider_id',sa.String(300),nullable=False),
        sa.Column('optout_token',sa.String(100),nullable=False,unique=True),sa.Column('sent_at',sa.DateTime(),nullable=True),
        sa.Column('response',sa.Text(),nullable=False),sa.UniqueConstraint('business_id','channel'))
    op.create_table('suppressions',sa.Column('recipient',sa.String(320),primary_key=True),sa.Column('reason',sa.String(100),nullable=False))
    for name in ('prospects','outreach'):
        op.create_index('ix_'+name+'_created_at',name,['created_at'])
    if op.get_bind().dialect.name == 'postgresql':
        for name in ('prospects','outreach','suppressions'):
            op.execute(f'ALTER TABLE public.{name} ENABLE ROW LEVEL SECURITY')
            op.execute(f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON public.{name} FROM anon; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON public.{name} FROM authenticated; END IF; END $$")

def downgrade():
    for name in ('outreach','prospects','suppressions'):
        op.drop_table(name)
