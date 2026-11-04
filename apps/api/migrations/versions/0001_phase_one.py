"""Phase one authentication and CRM schema."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None

def upgrade():
    def table(name, *columns, **kwargs):
        return op.create_table(name, sa.Column('id', sa.String(36), primary_key=True), sa.Column('created_at', sa.DateTime(), nullable=False), *columns, **kwargs)
    def text(name, length=200, nullable=False):
        return sa.Column(name, sa.String(length), nullable=nullable)
    def fk(name, target, nullable=False, cascade=False):
        return sa.Column(name, sa.String(36), sa.ForeignKey(target, ondelete='CASCADE' if cascade or target == 'businesses.id' else None), nullable=nullable)
    table('users', text('email',320), sa.Column('password_hash', sa.Text(), nullable=False), text('role',20), sa.UniqueConstraint('email'))
    table('sessions', fk('user_id','users.id',cascade=True), text('token_hash',64), text('csrf',64), sa.Column('expires_at',sa.DateTime(),nullable=False),sa.UniqueConstraint('token_hash'))
    table('password_recoveries',fk('user_id','users.id'),text('token_hash',64),sa.Column('expires_at',sa.DateTime(),nullable=False),sa.UniqueConstraint('token_hash'))
    table('businesses',text('name'),text('country',80),text('city',100),text('industry',100),sa.Column('description',sa.Text(),nullable=False),text('website',2048),text('website_status',40),text('status',40),text('source',80),sa.UniqueConstraint('name','country','city',name='uq_business_location'))
    table('business_contacts',fk('business_id','businesses.id'),text('email',320),text('phone',50))
    table('opportunities',fk('business_id','businesses.id'),text('stage',30),sa.Column('value',sa.Numeric(12,2),nullable=False),text('currency',3),sa.UniqueConstraint('business_id'))
    table('notes',fk('business_id','businesses.id'),fk('user_id','users.id'),sa.Column('body',sa.Text(),nullable=False))
    table('follow_ups',fk('business_id','businesses.id'),sa.Column('due_at',sa.DateTime(),nullable=False),sa.Column('body',sa.Text(),nullable=False),sa.Column('done',sa.Boolean(),nullable=False))
    table('audit_logs',fk('user_id','users.id',True),text('action',100),text('entity_id',36))
    op.create_table('preferences',sa.Column('key',sa.String(80),primary_key=True),sa.Column('value',sa.Text(),nullable=False))
    for name, columns in {'users':['created_at'],'sessions':['created_at','user_id'],'password_recoveries':['created_at','user_id'],'businesses':['created_at','name','country','industry','status'],'business_contacts':['created_at','business_id'],'opportunities':['created_at','stage'],'notes':['created_at','business_id'],'follow_ups':['created_at','business_id','due_at'],'audit_logs':['created_at']}.items():
        for column in columns:
            op.create_index(f'ix_{name}_{column}',name,[column])

def downgrade():
    for name in ['preferences','audit_logs','follow_ups','notes','opportunities','business_contacts','businesses','password_recoveries','sessions','users']:
        op.drop_table(name)
