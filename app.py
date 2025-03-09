# app.py
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room, rooms
import json
import os
import time
import uuid
from openai import OpenAI
import config

# 初始化Flask应用
app = Flask(__name__)
app.config.from_object(config)

# 初始化SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# 初始化DeepSeek客户端
client = OpenAI(
    api_key=config.DEEPSEEK_API_KEY,
    base_url=config.DEEPSEEK_BASE_URL
)

# 加载题库
stories = []

try:
    with open(config.STORIES_PATH, 'r', encoding='utf-8') as f:
        stories = json.load(f)
    print(f"成功从 {config.STORIES_PATH} 加载题库")
except Exception as e:
    print(f"加载题库出错: {e}")
    # 默认故事
    stories = [
        {
            "title": "神秘的水果",
            "surface": "有人拿着一个水果，经过桥边时掉进了河里，于是人们开始尖叫逃离。",
            "bottom": "这发生在一个迷信的村庄，村民们相信如果神圣的水果接触到河水，就会带来灾难。"
        }
    ]

# 游戏房间状态
# {room_id: {players: {username: {ready: bool, socket_id: str}}, current_story: int, ...}}
game_rooms = {}

# 主页路由
@app.route('/')
def index():
    return render_template('index.html')

# 单人游戏路由
@app.route('/single')
def single_game():
    return render_template('single_game.html')

# 双人游戏登录路由
@app.route('/dual/login', methods=['GET', 'POST'])
def dual_login():
    if request.method == 'POST':
        username = request.form.get('username')
        
        # 验证用户名
        if username in config.SPECIAL_USERNAMES:
            session['username'] = username
            return redirect(url_for('dual_game'))
        else:
            return render_template('dual_login.html', error="用户名不正确")
    
    return render_template('dual_login.html')

# 双人游戏房间路由
@app.route('/dual/game')
def dual_game():
    username = session.get('username')
    if not username or username not in config.SPECIAL_USERNAMES:
        return redirect(url_for('dual_login'))
    
    return render_template('dual_game.html', username=username)

# API路由：获取所有题目
@app.route('/api/stories', methods=['GET'])
def get_stories():
    story_titles = [(i, s['title']) for i, s in enumerate(stories)]
    return jsonify(story_titles)

# 其他API路由将在下一步添加

# 在app.py中添加以下WebSocket事件处理代码

# 用户连接事件
@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")

# 用户断开连接事件
@socketio.on('disconnect')
def handle_disconnect():
    print(f"Client disconnected: {request.sid}")
    username = session.get('username')
    
    # 查找玩家所在的房间
    for room_id, room_data in list(game_rooms.items()):
        players = room_data.get('players', {})
        
        # 检查玩家是否在此房间
        if username in players:
            handle_player_leave(username, room_id)
            break

# 处理玩家离开
def handle_player_leave(username, room_id):
    if room_id in game_rooms and username in game_rooms[room_id]['players']:
        # 从房间移除玩家
        leave_room(room_id)
        player_data = game_rooms[room_id]['players'].pop(username)
        
        # 通知房间内其他玩家
        emit('player_left', {'username': username}, to=room_id)
        
        # 检查房间是否还有其他玩家
        if game_rooms[room_id]['players']:
            # 还有其他玩家，检查离开的是否是房主
            if game_rooms[room_id].get('host') == username:
                # 离开的是房主，选择新房主
                new_host = next(iter(game_rooms[room_id]['players'].keys()))
                game_rooms[room_id]['host'] = new_host
                emit('new_host', {'host': new_host}, to=room_id)
        else:
            # 房间没有玩家了，设置过期时间
            game_rooms[room_id]['expire_time'] = time.time() + config.ROOM_TIMEOUT
            
    # 清理过期房间
    cleanup_expired_rooms()

# 清理过期房间
def cleanup_expired_rooms():
    current_time = time.time()
    for room_id in list(game_rooms.keys()):
        if 'expire_time' in game_rooms[room_id] and game_rooms[room_id]['expire_time'] < current_time:
            del game_rooms[room_id]
            print(f"Room {room_id} expired and removed")

# 玩家加入游戏
@socketio.on('join_game')
def handle_join_game(data):
    username = session.get('username')
    if not username or username not in config.SPECIAL_USERNAMES:
        emit('error', {'message': '未授权的用户'})
        return
    
    # 查找现有房间或创建新房间
    room_id = find_or_create_room(username)
    
    # 加入Socket.IO房间
    join_room(room_id)
    
    # 更新玩家状态
    game_rooms[room_id]['players'][username] = {
        'socket_id': request.sid,
        'ready': False
    }
    
    # 如果房间没有房主，设置当前玩家为房主
    if 'host' not in game_rooms[room_id]:
        game_rooms[room_id]['host'] = username
    
    # 返回房间信息
    room_data = {
        'room_id': room_id,
        'players': list(game_rooms[room_id]['players'].keys()),
        'host': game_rooms[room_id]['host'],
        'current_story': game_rooms[room_id].get('current_story'),
        'game_started': game_rooms[room_id].get('game_started', False)
    }
    
    # 通知当前玩家
    emit('room_joined', room_data)
    
    # 通知房间内其他玩家
    emit('player_joined', {'username': username}, to=room_id, include_self=False)

# 查找或创建房间
def find_or_create_room(username):
    # 首先查找玩家是否已经在某个房间中
    for room_id, room_data in game_rooms.items():
        if username in room_data.get('players', {}):
            return room_id
        
        # 如果房间中只有一个玩家，并且不是当前玩家，则加入该房间
        if len(room_data.get('players', {})) == 1 and not room_data.get('game_started', False):
            # 确保房间未满且游戏未开始
            return room_id
    
    # 如果没有找到合适的房间，创建新房间
    room_id = str(uuid.uuid4())
    game_rooms[room_id] = {
        'players': {},
        'game_started': False
    }
    return room_id

# 玩家准备
@socketio.on('player_ready')
def handle_player_ready():
    username = session.get('username')
    if not username:
        return
    
    # 查找玩家所在的房间
    for room_id, room_data in game_rooms.items():
        if username in room_data.get('players', {}):
            # 设置玩家状态为准备
            room_data['players'][username]['ready'] = True
            
            # 通知房间内所有玩家
            emit('player_status_changed', {
                'username': username,
                'ready': True
            }, to=room_id)
            
            # 检查是否所有玩家都已准备
            check_all_ready(room_id)
            break

# 检查是否所有玩家都已准备
def check_all_ready(room_id):
    room_data = game_rooms.get(room_id)
    if not room_data:
        return
    
    players = room_data.get('players', {})
    all_ready = len(players) >= 2 and all(p.get('ready', False) for p in players.values())
    
    if all_ready and not room_data.get('game_started', False):
        # 所有玩家都已准备，可以开始游戏
        room_data['game_started'] = False  # 设为False，等待房主选择题目
        emit('all_players_ready', {}, to=room_id)

# 房主选择题目
@socketio.on('select_story')
def handle_select_story(data):
    username = session.get('username')
    story_id = data.get('story_id')
    
    if not username or not story_id:
        return
    
    # 查找玩家所在的房间
    for room_id, room_data in game_rooms.items():
        if username in room_data.get('players', {}) and room_data.get('host') == username:
            # 验证故事ID
            if story_id < 0 or story_id >= len(stories):
                emit('error', {'message': '无效的故事ID'})
                return
            
            # 更新房间状态
            room_data['current_story'] = story_id
            room_data['game_started'] = True
            room_data['current_turn'] = username  # 房主先提问
            room_data['question_count'] = 0
            room_data['game_history'] = []
            
            # 通知房间内所有玩家
            emit('game_started', {
                'story_id': story_id,
                'surface': stories[story_id]['surface'],
                'current_turn': username
            }, to=room_id)
            break

# 玩家提问
@socketio.on('submit_question')
def handle_submit_question(data):
    username = session.get('username')
    question = data.get('question', '').strip()
    
    if not username or not question:
        return
    
    # 查找玩家所在的房间
    for room_id, room_data in game_rooms.items():
        if (username in room_data.get('players', {}) and 
            room_data.get('game_started', False) and 
            room_data.get('current_turn') == username):
            
            # 获取当前故事
            story_id = room_data.get('current_story')
            if story_id is None:
                emit('error', {'message': '游戏尚未开始'})
                return
            
            current_story = stories[story_id]
            
            # 调用AI裁判
            judgment = ai_judge(
                current_story['surface'],
                current_story['bottom'],
                question,
                room_data.get('game_history', [])
            )
            
            # 更新游戏历史
            room_data.setdefault('game_history', []).append((username, question, judgment))
            
            # 判断是否猜对
            if "SUCCESS" in judgment:
                # 游戏结束，当前玩家获胜
                emit('game_over', {
                    'winner': username,
                    'final_question': question,
                    'surface': current_story['surface'],
                    'bottom': current_story['bottom']
                }, to=room_id)
                
                # 重置游戏状态但保持房间
                room_data['game_started'] = False
                room_data['current_story'] = None
                for player in room_data['players'].values():
                    player['ready'] = False
            else:
                # 游戏继续，切换玩家
                next_player = get_next_player(room_id, username)
                room_data['current_turn'] = next_player
                
                # 通知房间内所有玩家
                emit('question_answered', {
                    'username': username,
                    'question': question,
                    'judgment': judgment,
                    'next_turn': next_player
                }, to=room_id)
            
            break

# 获取下一个玩家
def get_next_player(room_id, current_player):
    players = list(game_rooms[room_id]['players'].keys())
    if len(players) <= 1:
        return current_player
    
    index = players.index(current_player)
    next_index = (index + 1) % len(players)
    return players[next_index]

# AI裁判逻辑
def ai_judge(surface, bottom, guess, history):
    # 准备历史问答记录
    history_text = ""
    if history:
        history_text = "历史问答记录:\n"
        for i, (player, q, a) in enumerate(history):
            history_text += f"玩家{player} 问{i+1}: {q}\n答{i+1}: {a}\n"

    prompt = f"""作为海龟汤游戏的裁判，你知道完整的故事：
[汤面]: {surface}
[汤底]: {bottom}

玩家的问题或猜测是: "{guess}"

{history_text}

裁判规则：
1. 首先，分析玩家当前猜测与之前的问答历史，判断玩家是否已经猜出了足够还原整个事情真相的内容，如果玩家已经猜出了足够的内容，请回复"SUCCESS"
2. 如果玩家尚未猜出足够的内容和细节，则只回答"是"、"否"或"无关"三个选项之一:
   - "是"：当玩家提出的问题或猜测与汤底描述的事实相符合时
   - "否"：当玩家提出的问题或猜测与汤底描述的事实不符合时
   - "无关"：当玩家问题与解开谜题无关，或问了故事中未提及的细节时

严格要求：
- 不要给出任何提示、解释或额外信息
- 不要透露任何未被玩家猜到的汤底内容
- 回答必须只有一个词："SUCCESS"、"是"、"否"或"无关"
"""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=1.0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"AI调用出错: {e}")
        return "无关"  # 出错时返回默认回应

# 玩家取消准备
@socketio.on('player_unready')
def handle_player_unready():
    username = session.get('username')
    if not username:
        return
    
    # 查找玩家所在的房间
    for room_id, room_data in game_rooms.items():
        if username in room_data.get('players', {}):
            # 设置玩家状态为未准备
            room_data['players'][username]['ready'] = False
            
            # 通知房间内所有玩家
            emit('player_status_changed', {
                'username': username,
                'ready': False
            }, to=room_id)
            break

# 玩家离开房间
@socketio.on('leave_room')
def handle_leave_room():
    username = session.get('username')
    if not username:
        return
    
    # 查找玩家所在的房间
    for room_id, room_data in game_rooms.items():
        if username in room_data.get('players', {}):
            handle_player_leave(username, room_id)
            break

# 心跳检测
@socketio.on('heartbeat')
def handle_heartbeat():
    username = session.get('username')
    if not username:
        return
    
    # 更新最后活动时间
    for room_id, room_data in game_rooms.items():
        if username in room_data.get('players', {}):
            room_data['players'][username]['last_active'] = time.time()
            break









# 在app.py中添加或更新以下路由

# 路由：获取指定题目
@app.route('/api/story/<int:story_id>', methods=['GET'])
def get_story(story_id):
    if story_id < 0 or story_id >= len(stories):
        return jsonify({"error": "故事ID无效"}), 404

    # 初始化游戏状态
    session['current_story'] = story_id
    session['attempt_count'] = 0
    session['game_history'] = []
    session['game_solved'] = False

    # 确保session被保存
    session.modified = True

    return jsonify({
        "surface": stories[story_id]['surface'],
        "message": "请提问或猜测，AI裁判将回答：是、否、无关",
        "attempts_left": 10
    })

# 路由：提交猜测
@app.route('/api/guess', methods=['POST'])
def submit_guess():
    # 获取游戏状态并添加日志调试
    story_id = session.get('current_story')
    print(f"当前story_id: {story_id}")
    
    attempt_count = session.get('attempt_count', 0)
    game_history = session.get('game_history', [])
    game_solved = session.get('game_solved', False)

    # 校验游戏状态
    if story_id is None or story_id < 0 or story_id >= len(stories):
        print("错误：story_id无效或不存在")
        return jsonify({"error": "请先选择题目"}), 400

    if game_solved or attempt_count >= 10:
        return jsonify({"error": "游戏已结束"}), 400

    # 获取并处理猜测
    data = request.json
    guess = data.get('guess', '').strip()

    if not guess:
        return jsonify({"error": "请输入有效的问题或猜测"}), 400

    # 获取AI判断
    current_story = stories[story_id]
    judgment = ai_judge(
        current_story['surface'],
        current_story['bottom'],
        guess,
        game_history
    )
    
    # 判断是否成功
    if "SUCCESS" in judgment:
        game_solved = True
        session['game_solved'] = True

        # 基本成功信息 - 对所有题目都显示玩家最后的猜测
        result = {
            "judgment": "是",
            "success": True,
            "message": "🎉 恭喜你！成功猜出了核心内容！",
            "surface": current_story['surface'],
            "bottom": current_story['bottom'],
            "final_guess": guess
        }

        # 只有"巨人"故事才添加特殊消息
        if current_story.get('title') == "巨人":
            result["special_message"] = "希望你能快乐健康，早日寻得良人组成爱的巨人。"
    else:
        # 更新游戏状态
        attempt_count += 1
        session['attempt_count'] = attempt_count
        game_history.append((guess, judgment))
        session['game_history'] = game_history

        result = {"judgment": judgment, "success": False}

        # 检查是否达到最大次数
        if attempt_count >= 10:
            result["message"] = "🎮 游戏结束！已达到最大提问次数(10次)"
            result["surface"] = current_story['surface']
            result["bottom"] = current_story['bottom']
        else:
            result["message"] = f"🤖 AI裁判：{judgment}"
            result["attempts_left"] = 10 - attempt_count
            result["surface"] = current_story['surface']  # 确保在每次回答后都返回题目

    # 更新历史记录
    result["history"] = game_history
    
    # 确保session被保存
    session.modified = True
    
    return jsonify(result)

# 路由：查看答案
@app.route('/api/reveal', methods=['GET'])
def reveal_answer():
    story_id = session.get('current_story')

    if story_id is None or story_id < 0 or story_id >= len(stories):
        return jsonify({"error": "请先选择题目"}), 400

    current_story = stories[story_id]
    attempt_count = session.get('attempt_count', 0)

    result = {
        "surface": current_story['surface'],
        "bottom": current_story['bottom'],
        "attempts": attempt_count
    }

    # 添加特殊消息，如果是"巨人"故事
    if current_story.get('title') == "巨人":
        result["special_message"] = "希望你能快乐健康，早日寻得良人组成爱的巨人。"

    return jsonify(result)


    # 在app.py底部添加
if __name__ == '__main__':
    socketio.run(app, host=config.HOST, port=config.PORT, debug=config.DEBUG)