# Wk0_A2_coPlay.py
# Allows to you to chat while playing a game.
# Instantiates 2 webapps.

TESTING=False # Run tests

import datetime
import uuid
from flask import Flask, jsonify, request
from kazoo.client import KazooClient
import threading, time, zmq, base64, os, signal, json, requests, logging, random
logging.getLogger('werkzeug').disabled = True

class Webapp:
    # Creates front-end Flask endpoints on localhost:browser_port.
    # Creates listening ZMQ pull socket on zmq_port.
    # Creates sending ZMQ push sockets for each of webapp_ports.
    def __init__(self,browser_port,zmq_port,webapp_ports):
        app = Flask("webapp")
        app.add_url_rule("/","get_home",self.home,methods=['GET'])
        app.add_url_rule("/update","get_update",self.updates_get,methods=['GET'])
        app.add_url_rule("/tower","get_tower",self.tower_get,methods=['GET'])
        app.add_url_rule("/message","post_message",self.message_post,methods=['POST'])
        app.add_url_rule("/shutdown","get_shutdown",self.shutdown,methods=['GET'])
        app.add_url_rule("/start_game","get_start_game",self.start_game,methods=['GET'])
        app.add_url_rule("/current_state","get_current_state",self.get_current_state,methods=['GET'])
        app.add_url_rule("/chat_history","get_chat_history",self.get_chat_history,methods=['GET'])

        self.duplicates= set() #set will only keep unique messages (filter)
        self.game_state = [[1,2,3], [], []]
        self.chat_history = []
        self.selected_tower = None
        self.counter = 0 

        # Used week 7 tutorial as inspiration 
        # Wk7_kazoo_ZK.py   
        self.zk = KazooClient(hosts='127.0.0.1:2181')
        self.zk.start()
        if not self.zk.exists("/game_state"):
            self.zk.create("/game_state", json.dumps(self.game_state).encode('utf-8'))
        if not self.zk.exists("/chat_history"):
            self.zk.create("/chat_history", json.dumps(self.chat_history).encode('utf-8'))

        context = zmq.Context()
        self.pull_socket = context.socket(zmq.PULL)
        self.pull_socket.bind(f"tcp://127.0.0.1:{zmq_port}")
        other_sockets=[]
        for port in webapp_ports:
            push_socket = context.socket(zmq.PUSH)
            push_socket.connect(f"tcp://127.0.0.1:{port}")
            other_sockets+=[push_socket]
        self.other_sockets=other_sockets
        app.run(port=browser_port)

    #@app.route('/',methods=["GET"])
    # Called when a browser browses to, e.g. http://127.0.0.1:5000/
    # Returns front-end HTML5 coPlay.html.
    def home(self):
        with open('Wk0_A2_coPlay.html', 'r', encoding="utf-8") as file:
            content = file.read()
            return content

    # Sends a JSON message to all webapps, including itself.
    def broadcast(self, jsn): # {"message":solution_messages}
        jsn['id'] = str(uuid.uuid4())
        if random.random()>0.5:
            socket=self.other_sockets.pop()
            self.other_sockets=self.other_sockets+[socket]
        for socket in self.other_sockets:
            time.sleep(0.01)
            socket.send_json(jsn)

    #@app.route('/message',methods=["POST"])
    # Called when a browser sends a chat message.
    # The base64 message is decoded and sent to all webapps.
    def message_post(self):
        text = request.data # body of new message
        decoded_bytes = base64.b64decode(text)
        text = decoded_bytes.decode('utf-8')
        self.broadcast({"message":text})
        return "ok"

    #@app.route('/tower',methods=["GET"])
    # Called when a user clicks on a tower.
    # Broadcasts tower message to all webapps.
    def tower_get(self):
        tower= int(request.args['tower'])

        ######### Zookeeper Part #############
        data, _ = self.zk.get("/game_state")
        game_state = json.loads(data.decode('utf-8'))

        if self.selected_tower is None:
            if self.game_state[tower-1]: 
                self.selected_tower = tower
            

        elif self.selected_tower != tower:
            from_tower = self.selected_tower -1
            to_tower = tower-1
            
            if self.game_state[from_tower]:

                disk = self.game_state[from_tower][-1]

                #check if valid game move
                if not self.game_state[to_tower] or self.game_state[to_tower][-1] < disk:
                    self.game_state[from_tower].pop()
                    self.game_state[to_tower].append(disk)
                else:
                    print("Invalid move")

                # Reset after move
                self.selected_tower = None
        else:
            # Cancel selection
            self.selected_tower = None

        self.broadcast({"tower": tower,"state": self.game_state})
        if self.zk:
            self.zk.set("/game_state", json.dumps(self.game_state).encode("utf-8"))
        return "ok"

    #@app.route('/current_state',methods=["GET"])
    def get_current_state(self):
        ##### Zookeeper ######
        if self.zk and self.zk.exists("/game_state"):
            data, _ = self.zk.get("/game_state")
            return jsonify({"state": json.loads(data.decode("utf-8"))})
        
        return jsonify({"state":self.game_state})
    
    #@app.route("/chat/history", methods=["GET"])
    def get_chat_history(self):
        
        ##### Zookeeper ######
        if self.zk and self.zk.exists("/chat_history"):
            data, _ = self.zk.get("/chat_history")
            return jsonify({"chat": json.loads(data.decode("utf-8"))})

        return jsonify({self.chat_history})
    
    #@app.route('/update') #,methods=["GET"])
    # Called periodically by the polling browser.
    # Pulls all queued messages and them to browser for processing.
    def updates_get(self):
        messages=[]
        while True:
            try:
                ms = self.pull_socket.recv_json(zmq.NOBLOCK)
                msId = ms.get('id')
                
                current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

                if msId in self.duplicates:
                    continue  # Skip if already read
                self.duplicates.add(msId)

                if not TESTING:
                    print(f"[{current_time}] Message received on ZMQ port - {self.pull_socket.getsockopt(zmq.LAST_ENDPOINT).decode()} -> {ms}")
                else:
                    time.sleep(TESTING_DELAY)
                
                if "shutdown" in ms:
                    threading.Timer(1.0,self.do_shutdown).start()
                    return ms
                
                if "state" in ms:
                    self.game_state = ms["state"]

                # Save to chat history
                if "message" in ms:
                    self.chat_history.append(ms)
                    if len(self.chat_history) > 5:
                        self.chat_history.pop(0)  # keep only the last 5 messages
                    #print(self.chat_history)
                    if self.zk:
                        self.zk.set("/chat_history", json.dumps(self.chat_history).encode("utf-8"))
                
                messages=messages+[ms]
            except zmq.Again: 
                return json.dumps(messages)

    #@app.route('/shutdown')
    # You can ignore this method.
    # Returns a link to homepage - can be used for development purposes.
    def shutdown(self):
        self.broadcast({"shutdown":"shutdown"})
        return "<a href='/'>Home</a>"
    
    def do_shutdown(self):
        os.kill(os.getpid(), signal.SIGINT)

    #@app.route("/start_game")
    def start_game(self):
        num_disks = int(request.args.get("num_disks", 3))
        self.num_disks = num_disks
        self.game_state = [list(range(1, num_disks + 1)), [], []]
        
        self.broadcast({
        "state": self.game_state,
        "new_game": True,})

        return "ok"

# Thread target - start a peer by instantiating a Webapp.
def peer(browser_port,webapp_port,webapp_ports): 
    Webapp(browser_port,webapp_port,webapp_ports)

if TESTING: # Keep testing infrastucture stable.
    zmq_ports=[5001,5003,5005]
    threading.Thread(target=peer,args=(5000,5001,zmq_ports),daemon=TESTING).start()
    threading.Thread(target=peer,args=(5002,5003,zmq_ports),daemon=True).start()
    threading.Thread(target=peer,args=(5004,5005,zmq_ports),daemon=True).start()
else:
    zmq_ports=[5001,5003]
    threading.Thread(target=peer,args=(5000,5001,zmq_ports)).start()
    threading.Thread(target=peer,args=(5002,5003,zmq_ports),daemon=True).start()

TESTING_DELAY=0.0
# Remove messages to clean up after a test
def test_clean():
    time.sleep(0.1)
    url1 = 'http://127.0.0.1:5000/update'
    url2 = 'http://127.0.0.1:5002/update'
    url3 = 'http://127.0.0.1:5004/update'
    towers1=requests.get(url1).json()
    towers2=requests.get(url2).json()
    towers3=requests.get(url3).json()

# Test that simulates browser send a Hello world message.
# Checks if the same webapp can receive the sent message.
def test_message_hello_world():
    time.sleep(1)
    # Simulate GUI sending Hello
    url1 = 'http://127.0.0.1:5000/message'
    json_data = base64.b64encode("Hello world".encode('utf-8'))
    response_ignored = requests.post(url1, json_data)
    
    # Check the message has been broadcasted and is returned when requesting updates.
    url1 = 'http://127.0.0.1:5000/update'
    last_chat=requests.get(url1).json().pop()['message']
    return last_chat=="Hello world"

# test if invalid message sent 
def test_invalid_input():
    print("\nRunning test_invalid_input...")

    url = 'http://127.0.0.1:5000/message'
    invalid_msg = b"This is not base64 encoded"

    response = requests.post(url, invalid_msg)
    if response.status_code >= 400:
        print(f"PASS: Invalid input handled correctly and rejected with status {response.status_code}")
        return True
    else:
        print(f"FAIL: Server accepted invalid input. Status: {response.status_code}")
        return False

#test for unique messages and tower clicks
def test_unique_messages():
    print("\nRunning test_unique_message_delivery...")
    time.sleep(1)
    
    # Simulate GUI sending Hello
    url1 = 'http://127.0.0.1:5000/message'
    unique_text = f"TestMsg with ID {uuid.uuid4()}"
    json_data = base64.b64encode(unique_text.encode('utf-8'))
    requests.post(url1, json_data)

    # Simulate receiving Hello
    url2 = 'http://127.0.0.1:5000/update'
    messages = requests.get(url2).json()
    if not messages:
        print("Test failed: No messages received.")
        return False

    # Find unique message
    found = None
    for msg in messages:
        if msg.get('message') == unique_text:
            found = msg
            break
    
    if found is None:
        print("Test failed: Message was not received.")
        return False
   
    if "id" not in found:
        print("Test failed: 'id' field missing from received message.")
        return False

    print(f"PASS: Unique message received {found['message']}")

    # Call /update again to see message should NOT appear again
    second_batch = requests.get(url2).json()
    for msg in second_batch:
        if msg.get('id') == found['id']:
            print("Test failed: Duplicate message received on second /update call.")
            return False

    print("PASS: No duplicates received on second /update call")
    return True

# test tower clicks and verify state sync
def test_tower_click_state_sync():
    print("Testing tower click and state sync...")
    time.sleep(1)

    # Simulate GUI selecting a tower and moving to another tower
    requests.get("http://127.0.0.1:5000/tower?tower=1")
    requests.get("http://127.0.0.1:5000/tower?tower=3")

    # Get the updated game state from client 1
    url1 = "http://127.0.0.1:5000/update"
    state1 = requests.get(url1).json()

    # Get the updated game state from client 2
    url2 = "http://127.0.0.1:5002/update"
    state2 = requests.get(url2).json()

    latest_state1 = state1[-1]["state"] if state1 else None
    latest_state2 = state2[-1]["state"] if state2 else None

    if latest_state1 == latest_state2:
        print("PASS: Game state is synchronized across clients.")
        return True
    else:
        print("FAIL: Game state mismatch.")
        print(f"Client 1 state: {latest_state1}")
        print(f"Client 2 state: {latest_state2}")
        return False

# test message order 
def test_lag_reorder_tolerance():
    print("\nRunning test_lag_reorder_tolerance...")

    url = 'http://127.0.0.1:5000/message'
    msg1 = f"Msg Early {uuid.uuid4()}"
    msg2 = f"Msg Late {uuid.uuid4()}"

    # Send late message then early one with a delay
    threading.Thread(target=delayed_message, args=(url, msg1, 1)).start()
    threading.Thread(target=delayed_message, args=(url, msg2, 0.1)).start()

    time.sleep(2)

    messages = requests.get('http://127.0.0.1:5000/update').json()
    received = [msg['message'] for msg in messages]
    
    if msg1 in received and msg2 in received:
        print(received)
        print("PASS: Both messages received.")
        return True
    else:
        print("FAIL: One or both messages not received.")
        print("Messages received:", received)
        return False

def delayed_message(url, msg, delay):
        time.sleep(delay)
        requests.post(url, base64.b64encode(msg.encode('utf-8')))

# test message persistence with Zookeeper 
def test_chat_sync():
    print("\nTesting Zookeeper chat history sync...")

    found = False
    url1 = 'http://127.0.0.1:5000/message'
    url2 = 'http://127.0.0.1:5000/update'
    unique_text = f"TestMsg with ID {uuid.uuid4()}"
    json_data = base64.b64encode(unique_text.encode('utf-8'))
    
    requests.post(url1, json_data)
    time.sleep(0.5)

    requests.get(url2)
    time.sleep(0.5)

    zk = KazooClient(hosts='127.0.0.1:2181')
    zk.start()

    # Get chat data from Zookeeper
    if zk.exists("/chat_history"):
        data, stat = zk.get("/chat_history")
        zk.stop()

        if isinstance(data, bytes):
            chat_history = json.loads(data.decode('utf-8'))
        else:
            chat_history = json.loads(data)

        # Check if the expected message is in the chat history
        for msg in chat_history:
            if msg.get('message') == unique_text:
                found = True
                break
        
    if found:
        print("Test passed: Message found in Zookeeper chat history.")
        return True
    else:
        print("Test failed: Message not found in Zookeeper chat history.")
        return False


def tests():
    do_test_message_hello_world=True
    do_test_invalid_input = True
    do_test_unique_messages = True
    do_test_tower_click_state_sync = True
    do_test_lag_reorder_tolerance = True
    do_test_chat_sync = True

    if do_test_message_hello_world:
        print(f"test_message_hello_world: {test_message_hello_world()}")
        test_clean()
    if do_test_invalid_input:
        print(f"test_invalid_input: {test_invalid_input()}")
        test_clean()
    if do_test_unique_messages:
        print(f"test_unique_message_delivery: {test_unique_messages()}")
        test_clean()
    if do_test_tower_click_state_sync:
        print(f"test_tower_click_state_sync: {test_tower_click_state_sync()}")
        test_clean()
    if do_test_lag_reorder_tolerance:
        print(f"test_lag_order: {test_lag_reorder_tolerance()}")
        test_clean()
    if do_test_chat_sync:
        print(f"test_zookeeper_chat_sync: {test_chat_sync()}")

if TESTING:
    tests()
