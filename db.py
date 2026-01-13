import os
import json
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///koemi.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

pool_kwargs = {}
if "pooler.supabase.com" in DATABASE_URL:
    pool_kwargs = {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }

engine = create_engine(DATABASE_URL, **pool_kwargs)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True)
    auto_react = Column(Boolean, default=False)
    react_emoji = Column(String, default="*")
    remember_users = Column(Boolean, default=True)
    status = Column(String, default="lurking")
    activity_type = Column(String, default="watching")
    presence_status = Column(String, default="online")
    presence_text = Column(String, default="")
    presence_emoji = Column(String, default="")

class Channel(Base):
    __tablename__ = "channels"
    channel_id = Column(String, primary_key=True)
    reply_all = Column(Boolean, default=False)

class GuildPattern(Base):
    __tablename__ = "guild_patterns"
    guild_id = Column(String, primary_key=True)
    phrases = Column(JSON, default=[])
    words = Column(JSON, default=[])

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    guild_id = Column(String)
    user_id = Column(String)
    name = Column(String)
    pronouns = Column(String, default="not set")
    last_seen = Column(DateTime, default=datetime.now)
    data = Column(JSON, default={})

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True)
    guild_id = Column(String)
    user_id = Column(String)
    who = Column(String)
    text = Column(Text)
    timestamp = Column(DateTime, default=datetime.now)

Base.metadata.create_all(engine)

def get_session():
    return SessionLocal()

def migrate_schema():
    session = get_session()
    try:
        from sqlalchemy import text
        try:
            session.execute(text("ALTER TABLE conversations ALTER COLUMN user_id TYPE VARCHAR"))
            session.execute(text("ALTER TABLE users ALTER COLUMN user_id TYPE VARCHAR"))
            session.execute(text("ALTER TABLE settings ADD COLUMN IF NOT EXISTS react_emoji VARCHAR DEFAULT '*'"))
            session.commit()
            print("✓ Schema migration successful")
        except Exception as e:
            session.rollback()
            print(f"Schema migration skipped (likely already correct): {e}")
    finally:
        session.close()

try:
    migrate_schema()
except Exception as e:
    print(f"Migration error (non-critical): {e}")

def load_settings_db():
    session = get_session()
    try:
        from sqlalchemy import text
        try:
            session.execute(text("ALTER TABLE settings ADD COLUMN IF NOT EXISTS presence_status VARCHAR DEFAULT 'online'"))
            session.execute(text("ALTER TABLE settings ADD COLUMN IF NOT EXISTS presence_text VARCHAR DEFAULT ''"))
            session.execute(text("ALTER TABLE settings ADD COLUMN IF NOT EXISTS presence_emoji VARCHAR DEFAULT ''"))
            session.commit()
        except:
            session.rollback()
        
        setting = session.query(Settings).first()
        if not setting:
            setting = Settings()
            session.add(setting)
            session.commit()
        return {
            "auto_react": setting.auto_react,
            "react_emoji": getattr(setting, 'react_emoji', None) or "*",
            "remember_users": setting.remember_users,
            "status": setting.status,
            "activity_type": setting.activity_type,
            "presence_status": getattr(setting, 'presence_status', None) or "online",
            "presence_text": getattr(setting, 'presence_text', None) or "",
            "presence_emoji": getattr(setting, 'presence_emoji', None) or ""
        }
    finally:
        session.close()

def save_settings_db(s):
    session = get_session()
    try:
        setting = session.query(Settings).first()
        if not setting:
            setting = Settings()
        setting.auto_react = s.get("auto_react", False)
        setting.react_emoji = s.get("react_emoji", "*")
        setting.remember_users = s.get("remember_users", True)
        setting.status = s.get("status", "lurking")
        setting.activity_type = s.get("activity_type", "watching")
        setting.presence_status = s.get("presence_status", "online")
        setting.presence_text = s.get("presence_text", "")
        setting.presence_emoji = s.get("presence_emoji", "")
        session.add(setting)
        session.commit()
    finally:
        session.close()

def load_channels_db():
    session = get_session()
    try:
        channels_db = session.query(Channel).all()
        return {ch.channel_id: {"reply_all": ch.reply_all} for ch in channels_db}
    finally:
        session.close()

def save_channels_db(c):
    session = get_session()
    try:
        session.query(Channel).delete()
        for channel_id, data in c.items():
            ch = Channel(channel_id=channel_id, reply_all=data.get("reply_all", False))
            session.add(ch)
        session.commit()
    finally:
        session.close()

def load_guild_patterns_db():
    session = get_session()
    try:
        patterns_db = session.query(GuildPattern).all()
        return {p.guild_id: {"phrases": p.phrases if p.phrases else [], "words": p.words if p.words else []} for p in patterns_db}
    finally:
        session.close()

def save_guild_patterns_db(g):
    session = get_session()
    try:
        for guild_id, data in g.items():
            pattern = session.query(GuildPattern).filter_by(guild_id=guild_id).first()
            if not pattern:
                pattern = GuildPattern(guild_id=guild_id)
            pattern.phrases = data.get("phrases", [])
            pattern.words = data.get("words", [])
            session.add(pattern)
        session.commit()
    finally:
        session.close()

def load_memory_db():
    session = get_session()
    try:
        from sqlalchemy import text
        try:
            session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS pronouns VARCHAR DEFAULT 'not set'"))
            session.commit()
        except:
            session.rollback()
        
        users_data = {}
        for user in session.query(User).all():
            key = f"{user.guild_id}_{user.user_id}"
            user_data_dict = user.data if user.data else {}
            users_data[key] = {"name": user.name, "pronouns": getattr(user, 'pronouns', 'not set'), "last_seen": user.last_seen.isoformat() if user.last_seen else None, **user_data_dict}
        
        convos_data = {}
        for conv in session.query(Conversation).all():
            key = f"{conv.guild_id}_{conv.user_id}"
            if key not in convos_data:
                convos_data[key] = []
            convos_data[key].append({"who": conv.who, "text": conv.text})
        
        return {"users": users_data, "guilds": {}, "convos": convos_data}
    finally:
        session.close()

def save_memory_db(mem):
    session = get_session()
    try:
        session.query(User).delete()
        session.query(Conversation).delete()
        
        for user_key, user_data in mem.get("users", {}).items():
            if "_" in user_key:
                guild_id, user_id = user_key.rsplit("_", 1)
                user = User(
                    guild_id=guild_id,
                    user_id=user_id,
                    name=user_data.get("name", ""),
                    pronouns=user_data.get("pronouns", "not set"),
                    last_seen=datetime.fromisoformat(user_data.get("last_seen")) if user_data.get("last_seen") else datetime.now(),
                    data={k: v for k, v in user_data.items() if k not in ["name", "last_seen", "pronouns"]}
                )
                session.add(user)
        
        for convo_key, convo_list in mem.get("convos", {}).items():
            if "_" in convo_key:
                guild_id, user_id = convo_key.rsplit("_", 1)
                for conv in convo_list:
                    c = Conversation(
                        guild_id=guild_id,
                        user_id=user_id,
                        who=conv.get("who", ""),
                        text=conv.get("text", "")
                    )
                    session.add(c)
        
        session.commit()
    finally:
        session.close()
