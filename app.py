# ==============================================================================
#                 MINISTER MULTI-SERVER LIKE, VISIT & AUTO-LIKE API SYSTEM
# ==============================================================================

from flask import Flask, request, jsonify
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToDict
import binascii
import aiohttp
import requests
import json
import like_pb2
import like_count_pb2
import uid_generator_pb2
import time
from collections import defaultdict
from datetime import datetime, timedelta
import random
import os
import urllib.parse
import jwt
from byte import encrypt_api, Encrypt_ID

USER_API_KEY = "Lucky"
ADMIN_KEY = "909090"
KEY_LIMIT = 90

TOKEN_CACHE = {}
tracker = defaultdict(lambda: [0, time.time()])
liked_cache = defaultdict(set)

app = Flask(__name__)

def load_accounts(server_name):
    try:
        if server_name == "IND":
            filename = "account_ind.txt"
        elif server_name in {"BR", "US", "SAC", "NA"}:
            filename = "account_br.txt"
        else:
            filename = "account_bd.txt"

        if not os.path.exists(filename):
            filename = "account_ind.txt"
            if not os.path.exists(filename):
                return []

        accounts = []
        with open(filename, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if ':' in line:
                    parts = line.split(':', 1)
                    uid = parts[0].strip()
                    password = parts[1].strip()
                    if uid and password:
                        accounts.append({"uid": uid, "password": password})
        return accounts
    except Exception:
        return []

def load_tokens(server_name):
    try:
        path = "token_ind.json" if server_name == "IND" else ("token_br.json" if server_name in {"BR", "US", "SAC", "NA"} else "token_bd.json")
        if not os.path.exists(path):
            return []
        with open(path, "r") as f:
            data = json.load(f)
        return [item["token"] for item in data if "token" in item and item["token"] not in ["", "N/A"]]
    except Exception:
        return []

async def generate_jwt_token(uid, password):
    try:
        encoded_password = urllib.parse.quote(password)
        url = f"https://ff-jwt-gen-api.lovable.app/api/public/token?uid={uid}&password={encoded_password}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=24) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, dict):
                        return data.get('jwt_token') or data.get('token')
                return None
    except Exception:
        return None

async def get_valid_token(uid, password):
    if uid in TOKEN_CACHE:
        cached = TOKEN_CACHE[uid]
        if (cached["expires_at"] - datetime.utcnow()).total_seconds() > 1800:
            return cached["token"]

    token = await generate_jwt_token(uid, password)
    if not token:
        return None

    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        exp = payload.get("exp")
        TOKEN_CACHE[uid] = {"token": token, "expires_at": datetime.utcfromtimestamp(exp)}
    except Exception:
        TOKEN_CACHE[uid] = {"token": token, "expires_at": datetime.utcnow() + timedelta(hours=24)}

    return token

def encrypt_message(plaintext):
    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_message = pad(plaintext, AES.block_size)
    return binascii.hexlify(cipher.encrypt(padded_message)).decode('utf-8')

def create_protobuf_message(user_id, region):
    message = like_pb2.like()
    message.uid = int(user_id)
    message.region = region
    return message.SerializeToString()

async def send_like(encrypted_uid, token, url):
    try:
        edata = bytes.fromhex(encrypted_uid)
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB55"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=edata, headers=headers, timeout=5) as response:
                return response.status
    except Exception:
        return 500

async def process_account(target_uid, encrypted_uid, account, url, semaphore, server_name):
    async with semaphore:
        token = await get_valid_token(account['uid'], account['password'])
        if not token:
            return 500, account['uid']
        status = await send_like(encrypted_uid, token, url)
        if status == 200:
            liked_cache[target_uid].add(account['uid'])
        return status, account['uid']

async def send_all_likes(target_uid, server_name, url, limit=2000):
    protobuf_message = create_protobuf_message(target_uid, server_name)
    encrypted_uid = encrypt_message(protobuf_message)
    accounts = load_accounts(server_name)
    if not accounts:
        return {'success': 0, 'total': 0}

    already_liked = liked_cache.get(target_uid, set())
    fresh_accounts = [acc for acc in accounts if acc['uid'] not in already_liked]
    if not fresh_accounts:
        return {'success': 0, 'total': len(accounts)}

    random.shuffle(fresh_accounts)
    semaphore = asyncio.Semaphore(25)
    tasks = [
        process_account(target_uid, encrypted_uid, acc, url, semaphore, server_name)
        for acc in fresh_accounts[:limit]
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    successful = sum(1 for r in results if isinstance(r, tuple) and r[0] == 200)
    return {'success': successful, 'total': len(accounts)}

def enc(uid):
    message = uid_generator_pb2.uid_generator()
    message.krishna_ = int(uid)
    message.teamXdarks = 1
    return encrypt_message(message.SerializeToString())

def decode_protobuf(binary):
    try:
        items = like_count_pb2.Info()
        items.ParseFromString(binary)
        return MessageToDict(items, preserving_proto_field_name=True)
    except Exception:
        return {}

def extract_profile_details(dict_data):
    acc = dict_data.get('AccountInfo', dict_data)
    if not isinstance(acc, dict):
        acc = {}
    nickname = acc.get('PlayerNickname') or acc.get('nickname') or acc.get('Name') or 'Unknown'
    level = acc.get('Levels') or acc.get('level') or acc.get('Level') or 0
    likes = acc.get('Likes') or acc.get('likes') or 0
    br_rank = acc.get('BRRank') or acc.get('rank') or acc.get('BrRank') or 'N/A'
    cs_rank = acc.get('CSRank') or acc.get('csRank') or acc.get('CsRank') or 'N/A'
    region = acc.get('PlayerRegion') or acc.get('region') or 'IND'
    return {
        "nickname": nickname,
        "level": int(level),
        "likes": int(likes),
        "br_rank": str(br_rank),
        "cs_rank": str(cs_rank),
        "region": str(region)
    }

def get_player_info(encrypted_uid, server_name, token):
    url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow" if server_name == "IND" else (
        "https://client.us.freefiremobile.com/GetPlayerPersonalShow" if server_name in {"BR", "US", "SAC", "NA"} else
        "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"
    )
    edata = bytes.fromhex(encrypted_uid)
    headers = {
        'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        'Authorization': f"Bearer {token}",
        'Content-Type': "application/x-www-form-urlencoded",
        'X-GA': "v1 1",
        'ReleaseVersion': "OB55"
    }
    try:
        response = requests.post(url, data=edata, headers=headers, verify=False, timeout=10)
        return decode_protobuf(response.content)
    except Exception:
        return {}

async def visit_request(session, url, token, data):
    headers = {
        "ReleaseVersion": "OB55",
        "X-GA": "v1 1",
        "Authorization": f"Bearer {token}",
        "Host": url.replace("https://", "").split("/")[0]
    }
    try:
        async with session.post(url, headers=headers, data=data, ssl=False) as resp:
            if resp.status == 200:
                return True, await resp.read()
            return False, None
    except Exception:
        return False, None

async def send_until_target_success(tokens, uid, server_name, target_success=100):
    url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow" if server_name == "IND" else (
        "https://client.us.freefiremobile.com/GetPlayerPersonalShow" if server_name in {"BR", "US", "SAC", "NA"} else
        "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"
    )
    connector = aiohttp.TCPConnector(limit=0)
    total_success = 0
    total_sent = 0
    parsed_info = {}

    async with aiohttp.ClientSession(connector=connector) as session:
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)

        while total_success < target_success and total_sent < len(tokens) * 2:
            batch_size = min(target_success - total_success, 50)
            tasks = [
                asyncio.create_task(visit_request(session, url, tokens[(total_sent + i) % len(tokens)], data))
                for i in range(batch_size)
            ]
            results = await asyncio.gather(*tasks)

            for success, response in results:
                if success and response is not None and not parsed_info:
                    raw_dict = decode_protobuf(response)
                    if raw_dict:
                        parsed_info = extract_profile_details(raw_dict)

            batch_success = sum(1 for r, _ in results if r)
            total_success += batch_success
            total_sent += batch_size

    return total_success, parsed_info

# ==============================================================================
#                              API ENDPOINTS
# ==============================================================================

@app.route('/like', methods=['GET'])
def handle_like_requests():
    uid = request.args.get("uid")
    server_name = request.args.get("server_name", "IND").upper()
    key = request.args.get("key")
    count_req = int(request.args.get("count", 2000))

    if key != USER_API_KEY and key != ADMIN_KEY:
        return jsonify({"status": 403, "error": "Invalid API Key"}), 403

    accounts = load_accounts(server_name) or load_accounts("IND")
    if not accounts:
        return jsonify({"status": 500, "error": "No accounts loaded"}), 500

    check_token = None
    for account in accounts[:5]:
        check_token = asyncio.run(get_valid_token(account['uid'], account['password']))
        if check_token:
            break

    encrypted_uid = enc(uid)
    before = get_player_info(encrypted_uid, server_name, check_token)
    before_details = extract_profile_details(before)

    like_url = "https://client.ind.freefiremobile.com/LikeProfile" if server_name == "IND" else (
        "https://client.us.freefiremobile.com/LikeProfile" if server_name in {"BR", "US", "SAC", "NA"} else
        "https://clientbp.ggpolarbear.com/LikeProfile"
    )

    asyncio.run(send_all_likes(uid, server_name, like_url, limit=count_req))

    after = get_player_info(encrypted_uid, server_name, check_token)
    after_details = extract_profile_details(after)

    like_given = max(after_details['likes'] - before_details['likes'], 0)

    return jsonify({
        "status": "SUCCESS",
        "PlayerNickname": after_details['nickname'],
        "UID": int(uid),
        "LikesbeforeCommand": before_details['likes'],
        "LikesafterCommand": after_details['likes'],
        "LikesGivenByAPI": like_given,
        "level": after_details['level'],
        "br_rank": after_details['br_rank'],
        "cs_rank": after_details['cs_rank']
    })

@app.route('/visit', methods=['GET'])
def send_visits_route():
    uid = request.args.get("uid")
    server_name = request.args.get("server_name", "IND").upper()
    key = request.args.get("key")
    count_limit = int(request.args.get("count", 100))

    if key != USER_API_KEY and key != ADMIN_KEY:
        return jsonify({"status": 403, "error": "Invalid API Key"}), 403

    tokens = load_tokens(server_name)
    if not tokens:
        accounts = load_accounts(server_name) or load_accounts("IND")
        for acc in accounts[:20]:
            t = asyncio.run(get_valid_token(acc['uid'], acc['password']))
            if t:
                tokens.append(t)

    total_success, profile_info = asyncio.run(send_until_target_success(tokens, uid, server_name, target_success=count_limit))

    return jsonify({
        "status": "SUCCESS",
        "uid": int(uid),
        "success": total_success,
        "nickname": profile_info.get("nickname", "Unknown"),
        "level": profile_info.get("level", 0),
        "likes": profile_info.get("likes", 0),
        "br_rank": profile_info.get("br_rank", "N/A"),
        "cs_rank": profile_info.get("cs_rank", "N/A"),
        "region": profile_info.get("region", server_name)
    })

@app.route('/info', methods=['GET'])
def get_info_bot_data():
    uid = request.args.get("uid")
    server_name = request.args.get("server_name", "IND").upper()
    key = request.args.get("key")

    if key != USER_API_KEY and key != ADMIN_KEY:
        return jsonify({"status": 403, "error": "Invalid API Key"}), 403

    accounts = load_accounts(server_name) or load_accounts("IND")
    token = None
    for account in accounts[:5]:
        token = asyncio.run(get_valid_token(account['uid'], account['password']))
        if token:
            break

    encrypted_uid = enc(uid)
    raw_dict = get_player_info(encrypted_uid, server_name, token)
    extracted = extract_profile_details(raw_dict)

    return jsonify({
        "status": "SUCCESS",
        "nickname": extracted['nickname'],
        "uid": int(uid),
        "level": extracted['level'],
        "likes": extracted['likes'],
        "br_rank": extracted['br_rank'],
        "cs_rank": extracted['cs_rank'],
        "region": extracted['region']
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)
    