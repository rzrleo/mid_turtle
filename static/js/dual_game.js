// static/js/dual_game.js

// 初始化Socket.IO
function initSocketIO() {
    socket = io();
    
    // 连接事件
    socket.on('connect', function() {
        console.log('Connected to server');
        // 加入游戏
        socket.emit('join_game');
    });
    
    // 断开连接事件
    socket.on('disconnect', function() {
        console.log('Disconnected from server');
        document.getElementById('roomStatus').textContent = '已断开连接';
    });
    
    // 错误事件
    socket.on('error', function(data) {
        alert('错误: ' + data.message);
    });
    
    // 加入房间事件
    socket.on('room_joined', function(data) {
        console.log('Joined room:', data);
        
        // 更新房间信息
        document.getElementById('roomStatus').textContent = '已连接 - 房间ID: ' + data.room_id;
        
        // 更新玩家列表
        updatePlayersList(data.players);
        
        // 检查是否是房主
        isHost = (data.host === username);
        updateHostControls();
        
        // 检查游戏是否已经开始
        if (data.game_started && data.current_story !== null) {
            startGame(data.current_story);
        }
    });
    
    // 玩家加入事件
    socket.on('player_joined', function(data) {
        console.log('Player joined:', data.username);
        
        // 获取当前玩家列表并添加新玩家
        const playersList = document.getElementById('playersList');
        const playerItem = document.createElement('li');
        playerItem.textContent = data.username;
        playerItem.dataset.username = data.username;
        playerItem.dataset.ready = 'false';
        playersList.appendChild(playerItem);
    });
    
    // 玩家离开事件
    socket.on('player_left', function(data) {
        console.log('Player left:', data.username);
        
        // 从玩家列表中移除
        const playerItem = document.querySelector(`#playersList li[data-username="${data.username}"]`);
        if (playerItem) {
            playerItem.remove();
        }
    });
    
    // 新房主事件
    socket.on('new_host', function(data) {
        console.log('New host:', data.host);
        
        // 更新房主状态
        isHost = (data.host === username);
        updateHostControls();
    });
    
    // 玩家状态变化事件
    socket.on('player_status_changed', function(data) {
        console.log('Player status changed:', data);
        
        // 更新玩家准备状态
        const playerItem = document.querySelector(`#playersList li[data-username="${data.username}"]`);
        if (playerItem) {
            playerItem.dataset.ready = data.ready ? 'true' : 'false';
            playerItem.className = data.ready ? 'ready' : '';
        }
    });
    
    // 所有玩家准备事件
    socket.on('all_players_ready', function() {
        console.log('All players ready');
        
        if (isHost) {
            // 启用开始游戏按钮
            document.getElementById('startGameBtn').disabled = false;
        }
    });
    
    // 游戏开始事件
    socket.on('game_started', function(data) {
        console.log('Game started:', data);
        
        // 开始游戏
        startGame(data.story_id, data.surface, data.current_turn);
    });
    
    // 问题回答事件
    socket.on('question_answered', function(data) {
        console.log('Question answered:', data);
        
        // 添加问题和回答到历史记录
        addToHistory(data.username, data.question, data.judgment);
        
        // 更新当前回合
        isMyTurn = (data.next_turn === username);
        updateTurnIndicator(data.next_turn);
        
        // 启用/禁用问题输入
        document.getElementById('questionInput').disabled = !isMyTurn;
        document.getElementById('submitQuestionBtn').disabled = !isMyTurn;
    });
    
    // 游戏结束事件
    socket.on('game_over', function(data) {
        console.log('Game over:', data);
        
        // 显示游戏结果
        showGameOver(data);
    });
    
    // 设置心跳检测
    setInterval(function() {
        if (socket.connected) {
            socket.emit('heartbeat');
        }
    }, 30000); // 每30秒发送一次
}

// 初始化事件监听器
function initEventListeners() {
    // 准备按钮
    document.getElementById('readyBtn').addEventListener('click', function() {
        socket.emit('player_ready');
        isReady = true;
        document.getElementById('readyBtn').style.display = 'none';
        document.getElementById('unreadyBtn').style.display = 'inline-block';
    });
    
    // 取消准备按钮
    document.getElementById('unreadyBtn').addEventListener('click', function() {
        socket.emit('player_unready');
        isReady = false;
        document.getElementById('readyBtn').style.display = 'inline-block';
        document.getElementById('unreadyBtn').style.display = 'none';
    });
    
    // 离开房间按钮
    document.getElementById('leaveBtn').addEventListener('click', function() {
        socket.emit('leave_room');
        window.location.href = '/';
    });
    
    // 开始游戏按钮
    document.getElementById('startGameBtn').addEventListener('click', function() {
        const storyId = document.getElementById('storyDropdown').value;
        if (storyId) {
            socket.emit('select_story', { story_id: parseInt(storyId) });
        } else {
            alert('请选择一个题目');
        }
    });
    
    // 提交问题按钮
    document.getElementById('submitQuestionBtn').addEventListener('click', function() {
        const question = document.getElementById('questionInput').value.trim();
        if (question) {
            socket.emit('submit_question', { question: question });
            document.getElementById('questionInput').value = '';
            
            // 禁用输入，等待服务器响应
            document.getElementById('questionInput').disabled = true;
            document.getElementById('submitQuestionBtn').disabled = true;
        } else {
            alert('请输入有效的问题或猜测');
        }
    });
    
    // 再来一局按钮
    document.getElementById('playAgainBtn').addEventListener('click', function() {
        // 隐藏游戏结束屏幕
        document.getElementById('gameOverScreen').style.display = 'none';
        document.getElementById('waitingRoom').style.display = 'block';
        
        // 重置准备状态
        isReady = false;
        document.getElementById('readyBtn').style.display = 'inline-block';
        document.getElementById('unreadyBtn').style.display = 'none';
    });
    
    // 监听页面可见性变化
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') {
            // 页面可见时，检查连接状态
            if (socket && !socket.connected) {
                // 如果断开连接，尝试重连
                socket.connect();
            }
        }
    });
    
    // 监听页面关闭事件
    window.addEventListener('beforeunload', function(e) {
        if (gameStarted) {
            // 游戏进行中，提示用户
            e.preventDefault();
            e.returnValue = '游戏正在进行中，确定要离开吗？';
        }
    });
}

// 加载故事列表
function loadStories() {
    fetch('/api/stories')
        .then(response => response.json())
        .then(data => {
            const dropdown = document.getElementById('storyDropdown');
            
            // 清空下拉菜单
            dropdown.innerHTML = '<option value="" selected disabled>请选择题目</option>';
            
            // 添加故事选项
            data.forEach(([id, title]) => {
                const option = document.createElement('option');
                option.value = id;
                option.textContent = title;
                dropdown.appendChild(option);
            });
        })
        .catch(error => {
            console.error('获取故事列表失败:', error);
            alert('加载故事列表失败，请刷新页面重试');
        });
}

// 更新玩家列表
function updatePlayersList(players) {
    const playersList = document.getElementById('playersList');
    playersList.innerHTML = '';
    
    players.forEach(player => {
        const playerItem = document.createElement('li');
        playerItem.textContent = player;
        playerItem.dataset.username = player;
        playerItem.dataset.ready = 'false';
        playersList.appendChild(playerItem);
    });
}

// 更新房主控制面板
function updateHostControls() {
    const hostControls = document.getElementById('hostControls');
    
    if (isHost) {
        hostControls.style.display = 'block';
    } else {
        hostControls.style.display = 'none';
    }
}

// 开始游戏
function startGame(storyId, surface, currentTurn) {
    gameStarted = true;
    
    // 隐藏等待房间，显示游戏区域
    document.getElementById('waitingRoom').style.display = 'none';
    document.getElementById('gameRoom').style.display = 'block';
    
    // 如果提供了故事表面，则显示
    if (surface) {
        document.getElementById('storySurface').textContent = `汤面：${surface}`;
    } else {
        // 如果未提供，尝试通过API获取
        fetch(`/api/story/${storyId}`)
            .then(response => response.json())
            .then(data => {
                document.getElementById('storySurface').textContent = `汤面：${data.surface}`;
            })
            .catch(error => {
                console.error('获取故事失败:', error);
            });
    }
    
    // 更新当前回合指示器
    isMyTurn = (currentTurn === username);
    updateTurnIndicator(currentTurn);
    
    // 启用/禁用问题输入
    document.getElementById('questionInput').disabled = !isMyTurn;
    document.getElementById('submitQuestionBtn').disabled = !isMyTurn;
    
    // 清空历史记录
    document.getElementById('historyContent').innerHTML = '';
}

// 更新当前回合指示器
function updateTurnIndicator(currentTurn) {
    const turnElement = document.getElementById('currentTurn');
    
    if (currentTurn === username) {
        turnElement.textContent = '轮到你提问了！';
        turnElement.className = 'current-turn my-turn';
    } else {
        turnElement.textContent = `轮到 ${currentTurn} 提问`;
        turnElement.className = 'current-turn other-turn';
    }
}

// 添加到历史记录
function addToHistory(playerName, question, answer) {
    const historyContent = document.getElementById('historyContent');
    const historyItem = document.createElement('div');
    historyItem.className = 'history-item';
    
    const isCurrentUser = (playerName === username);
    
    const questionElement = document.createElement('div');
    questionElement.className = isCurrentUser ? 'question my-question' : 'question other-question';
    questionElement.textContent = `${playerName}: ${question}`;
    
    const answerElement = document.createElement('div');
    answerElement.className = 'answer';
    answerElement.textContent = `裁判: ${answer}`;
    
    historyItem.appendChild(questionElement);
    historyItem.appendChild(answerElement);
    historyContent.appendChild(historyItem);
    
    // 滚动到底部
    historyContent.scrollTop = historyContent.scrollHeight;
}

// 显示游戏结束
function showGameOver(data) {
    // 隐藏游戏区域，显示结束屏幕
    document.getElementById('gameRoom').style.display = 'none';
    document.getElementById('gameOverScreen').style.display = 'block';
    
    // 设置游戏结果
    const resultElement = document.getElementById('gameResult');
    const isWinner = (data.winner === username);
    
    if (isWinner) {
        resultElement.innerHTML = `<p class="winner-message">恭喜你获胜了！</p>
                                   <p>你猜对了答案: ${data.final_question}</p>`;
    } else {
        resultElement.innerHTML = `<p class="loser-message">玩家 ${data.winner} 获胜</p>
                                   <p>获胜猜测: ${data.final_question}</p>`;
    }
    
    // 显示完整故事
    const storyElement = document.getElementById('storyComplete');
    storyElement.innerHTML = `<div class="story-surface">汤面: ${data.surface}</div>
                              <div class="story-bottom">汤底: ${data.bottom}</div>`;
    
    // 重置游戏状态
    gameStarted = false;
}