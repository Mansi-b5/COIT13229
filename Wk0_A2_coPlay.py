# Wk0_A2_coPlay.py
# Allows to you to chat while playing a game.
# Instantiates 2 webapps.

TESTING=False # Run tests

from flask import Flask, request
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
        tower=request.args['tower']
        self.broadcast({"tower":tower})
        return "ok"

    #@app.route('/update') #,methods=["GET"])
    # Called periodically by the polling browser.
    # Pulls all queued messages and them to browser for processing.
    def updates_get(self):
        messages=[]
        while True:
            try:
                ms = self.pull_socket.recv_json(zmq.NOBLOCK)
                if not TESTING:
                    print(ms)
                else:
                    time.sleep(TESTING_DELAY)
                if "shutdown" in ms:
                    threading.Timer(1.0,self.do_shutdown).start()
                    return ms
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

def tests():
    do_test_message_hello_world=True
    if do_test_message_hello_world:
        print(f"test_message_hello_world: {test_message_hello_world()}")
        test_clean()

if TESTING:
    tests()
