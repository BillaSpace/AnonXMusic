# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic

from random import randint
from time import time
from motor.motor_asyncio import AsyncIOMotorClient

from anony import config, logger, userbot


class MongoDB:
    def __init__(self):
        """Initialize MongoDB connection and collections."""
        self.mongo = AsyncIOMotorClient(config.MONGO_URL, serverSelectionTimeoutMS=12500)
        self.db = self.mongo.Anon

        # Runtime caches
        self.admin_list = {}
        self.active_calls = {}
        self.blacklisted = []
        self.notified = []
        self.logger_status = False
        self.assistant = {}
        self.auth = {}
        self.chats = []
        self.lang = {}
        self.play_mode = {}
        self.users = []

        # Collections
        self.cache = self.db.cache
        self.assistantdb = self.db.assistant
        self.authdb = self.db.auth
        self.chatsdb = self.db.chats
        self.langdb = self.db.lang
        self.playmodedb = self.db.play
        self.usersdb = self.db.users
        
    # --------------------------- CONNECTION --------------------------- #
    async def connect(self) -> None:
        """Connect to MongoDB and pre-load cache."""
        try:
            start = time()
            await self.mongo.admin.command("ping")
            logger.info(f"Database connection successful. ({time() - start:.2f}s)")
            await self.load_cache()
        except Exception as e:
            raise SystemExit(f"Database connection failed: {type(e).__name__}") from e

    async def close(self) -> None:
        """Close MongoDB connection."""
        self.mongo.close()
        logger.info("Database connection closed.")

    # --------------------------- CALLS --------------------------- #
    async def get_call(self, chat_id: int) -> bool:
        return chat_id in self.active_calls

    async def add_call(self, chat_id: int) -> None:
        self.active_calls[chat_id] = 1

    async def remove_call(self, chat_id: int) -> None:
        self.active_calls.pop(chat_id, None)

    async def playing(self, chat_id: int, paused: bool = None) -> bool | None:
        if paused is not None:
            self.active_calls[chat_id] = int(not paused)
        return bool(self.active_calls.get(chat_id, 0))

    # --------------------------- ADMINS --------------------------- #
    async def get_admins(self, chat_id: int, reload: bool = False) -> list[int]:
        from anony.helpers._admins import reload_admins
        if chat_id not in self.admin_list or reload:
            self.admin_list[chat_id] = await reload_admins(chat_id)
        return self.admin_list[chat_id]

    # --------------------------- AUTH --------------------------- #
    async def _get_auth(self, chat_id: int) -> set[int]:
        if chat_id not in self.auth:
            doc = await self.authdb.find_one({"_id": chat_id}) or {}
            self.auth[chat_id] = set(doc.get("user_ids", []))
        return self.auth[chat_id]

    async def is_auth(self, chat_id: int, user_id: int) -> bool:
        return user_id in await self._get_auth(chat_id)

    async def add_auth(self, chat_id: int, user_id: int) -> None:
        users = await self._get_auth(chat_id)
        if user_id not in users:
            users.add(user_id)
            await self.authdb.update_one(
                {"_id": chat_id}, {"$addToSet": {"user_ids": user_id}}, upsert=True
            )

    async def rm_auth(self, chat_id: int, user_id: int) -> None:
        users = await self._get_auth(chat_id)
        if user_id in users:
            users.discard(user_id)
            await self.authdb.update_one(
                {"_id": chat_id}, {"$pull": {"user_ids": user_id}}
            )

    # --------------------------- ASSISTANTS --------------------------- #
    async def set_assistant(self, chat_id: int) -> int:
        num = randint(1, len(userbot.clients))
        await self.assistantdb.update_one(
            {"_id": chat_id}, {"$set": {"num": num}}, upsert=True
        )
        self.assistant[chat_id] = num
        return num

    async def get_assistant(self, chat_id: int):
        from anony import anon
        if chat_id not in self.assistant:
            doc = await self.assistantdb.find_one({"_id": chat_id})
            num = doc["num"] if doc else await self.set_assistant(chat_id)
            self.assistant[chat_id] = num
        return anon.clients[self.assistant[chat_id] - 1]

    async def get_client(self, chat_id: int):
        if chat_id not in self.assistant:
            await self.get_assistant(chat_id)
        return {
            1: getattr(userbot, "one", None),
            2: getattr(userbot, "two", None),
            3: getattr(userbot, "three", None),
        }.get(self.assistant.get(chat_id), userbot.one)

    # --------------------------- PLAY MODE --------------------------- #
    async def set_mode(self, chat_id: int, mode: str) -> None:
        await self.playmodedb.update_one(
            {"_id": chat_id},
            {"$set": {"mode": mode.lower()}},
            upsert=True,
        )
        self.play_mode[chat_id] = mode.lower()

    async def get_mode(self, chat_id: int) -> str:
        if chat_id not in self.play_mode:
            doc = await self.playmodedb.find_one({"_id": chat_id})
            self.play_mode[chat_id] = doc["mode"] if doc else "youtube"
        return self.play_mode[chat_id]

    # --------------------------- LOGGER --------------------------- #
    async def get_logger(self) -> bool:
        doc = await self.cache.find_one({"_id": "logger"})
        if doc:
            self.logger_status = doc["status"]
        return self.logger_status

    async def set_logger(self, status: bool) -> None:
        self.logger_status = status
        await self.cache.update_one(
            {"_id": "logger"}, {"$set": {"status": status}}, upsert=True
        )

    async def is_logger(self) -> bool:
        return self.logger_status

    # --------------------------- BLACKLIST --------------------------- #
    async def add_blacklist(self, chat_id: int) -> None:
        if str(chat_id).startswith("-"):
            self.blacklisted.append(chat_id)
            await self.cache.update_one(
                {"_id": "bl_chats"}, {"$addToSet": {"chat_ids": chat_id}}, upsert=True
            )
        else:
            await self.cache.update_one(
                {"_id": "bl_users"}, {"$addToSet": {"user_ids": chat_id}}, upsert=True
            )

    async def del_blacklist(self, chat_id: int) -> None:
        if str(chat_id).startswith("-"):
            if chat_id in self.blacklisted:
                self.blacklisted.remove(chat_id)
            await self.cache.update_one(
                {"_id": "bl_chats"}, {"$pull": {"chat_ids": chat_id}}
            )
        else:
            await self.cache.update_one(
                {"_id": "bl_users"}, {"$pull": {"user_ids": chat_id}}
            )

    async def get_blacklisted(self, chat: bool = False) -> list[int]:
        if chat:
            if not self.blacklisted:
                doc = await self.cache.find_one({"_id": "bl_chats"})
                self.blacklisted.extend(doc.get("chat_ids", []) if doc else [])
            return self.blacklisted
        doc = await self.cache.find_one({"_id": "bl_users"})
        return doc.get("user_ids", []) if doc else []

    # --------------------------- CHATS --------------------------- #
    async def is_chat(self, chat_id: int) -> bool:
        return chat_id in self.chats

    async def add_chat(self, chat_id: int) -> None:
        if not await self.is_chat(chat_id):
            self.chats.append(chat_id)
            await self.chatsdb.insert_one({"_id": chat_id})

    async def rm_chat(self, chat_id: int) -> None:
        if await self.is_chat(chat_id):
            self.chats.remove(chat_id)
            await self.chatsdb.delete_one({"_id": chat_id})

    async def get_chats(self) -> list:
        if not self.chats:
            self.chats.extend([chat["_id"] async for chat in self.chatsdb.find()])
        return self.chats

    # --------------------------- USERS --------------------------- #
    async def is_user(self, user_id: int) -> bool:
        return user_id in self.users

    async def add_user(self, user_id: int) -> None:
        if not await self.is_user(user_id):
            self.users.append(user_id)
            await self.usersdb.insert_one({"_id": user_id})

    async def rm_user(self, user_id: int) -> None:
        if await self.is_user(user_id):
            self.users.remove(user_id)
            await self.usersdb.delete_one({"_id": user_id})
    
    async def get_users(self) -> list:
        if not self.users:
            self.users.extend([user["_id"] async for user in self.usersdb.find()])
        return self.users

    # --------------------------- SUDOERS --------------------------- #
    async def add_sudo(self, user_id: int) -> None:
        await self.cache.update_one(
            {"_id": "sudoers"}, {"$addToSet": {"user_ids": user_id}}, upsert=True
        )

    async def del_sudo(self, user_id: int) -> None:
        await self.cache.update_one(
            {"_id": "sudoers"}, {"$pull": {"user_ids": user_id}}
        )

    async def get_sudoers(self) -> list[int]:
        doc = await self.cache.find_one({"_id": "sudoers"})
        return doc.get("user_ids", []) if doc else []

    # --------------------------- CACHE LOAD --------------------------- #
    async def load_cache(self) -> None:
        await self.get_chats()
        await self.get_users()
        await self.get_blacklisted(True)
        await self.get_logger()
        logger.info("Database cache loaded.")
