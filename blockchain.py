import hashlib
import json
from time import time
from uuid import uuid4
from textwrap import dedent

from flask import Flask, jsonify, request

from urllib.parse import urlparse
import requests


class BlockChain(object):
    def __init__(self):
        self.chain = []
        self.current_transactions = []

        #Create Genesis
        self.newBlock(previousHash=1, proof=100)

        #Nodes set
        self.nodes = set()

    
    def newBlock(self, proof, previousHash=None):
        """
        Creates a new block and add it to the chain
            :param proof: <int> Proof given by the PoW Algorithm
            :param previousHash: (Optional) <str> Hash of prev Block
            :return: <dict> New Block
        """
        
        block = {
            'index': len(self.chain)+1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previousHash': previousHash or self.hash(self.chain[-1]),
        }
        #Reset the current list of transactions
        self.current_transactions = []
        self.chain.append(block)

        return block


    def newTransaction(self, sender, receiver, amount):
        #Adds a new transaction to the list of the transaction
        """
        Creates a new transaction to go into the next mined Block
            :param sender: <str> Address of the Sender
            :param recipient: <str> Address of the Recipient
            :param amount: <int> Amount
            :return: <int> The index of the Block that will hold this transaction
        """

        self.current_transactions.append({
            'sender': sender,
            'receiver': receiver,
            'amount': amount,
        })

        return self.lastBlock['index']+1

    @staticmethod
    def hash(block):
        """
        Creates a SHA-256 hash of a block
            :param block: <dict> Block
            :return: <str>
        """
        #To avoid inconsistent hashes we'll sort the dictionary
        blockString = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(blockString).hexdigest()


    def proofOfWork(self, lastProof):
        """
        Simple PoW Algorithm - Principle: A solution that is difficult to find but easy to verify
         - Find a number p' such that hash(pp') contains leading 4 zeroes, where p is the previous p'
         - p is the previous proof, and p' is the new proof

            :param last_proof: <int>
            :return: <int>
        """
        proof = 0
        while(self.validProof(lastProof, proof) is False):
            proof += 1
        
        return proof

    @staticmethod
    def validProof(lastProof, proof):
        """
        Validates the Proof: Does hash(last_proof, proof) contain 4 leading zeroes?
            :param last_proof: <int> Previous Proof
            :param proof: <int> Current Proof
            :return: <bool> True if correct, False if not.
        """
        hit = f'{lastProof}{proof}'.encode()    #Guess Hit
        hashHit = hashlib.sha256(hit).hexdigest()
        return hashHit[:4] == "0000"
 
    @property
    def lastBlock(self):
        #Returns the last block in the chain
        return self.chain[-1]

    def registerNode(self, address):
        """
        Add a new node to the list of the nodes
            :param address: <str> Address of the node. Eg. 192.127.0.1:5000
            :return: None
        """
        parsedUrl = urlparse(address)
        self.nodes.add(parsedUrl.netloc)

    def validChain(self, chain):
        """
        Determine if the given blockchain is valid or not
            :param chain: <list> A Blockchain
            :return: <bool> True/False about the chain validity
        """
        lastBlock = chain[0]
        currentIndex = 1
        
        while currentIndex < len(self.chain):
            block = chain[currentIndex]
            print(f'{lastBlock}')
            print(f'{block}')
            print("\n-----------\n")
            
            #Check if the hash of the block is correct
            if (block['previousHash'] != self.hash(lastBlock)):
                return False
            
            #Check if the PoW of the block is correct
            if (not self.validProof(lastBlock['proof'], block['proof'])):
                return False
            
            lastBlock = block
            currentIndex+=1

        return True

    def resolveConflicts(self):
        """
        Consensus Algorithm: Resolves conflict when nodes show different chain by selecting
        and replacing the chains with the longest verified chain in the network.
        :return: <bool> True if the chain was replaced else False 
        """

        neighbours = self.nodes
        newChain = None

        #Find chain the longest chain
        maxLength = len(self.chain)

        #Iterate & verify all the chains from all the nodes in our network
        for node in neighbours:
            response = requests.get(f'http://{node}/chain')
            if (response.status_code == 200):
                length = response.json()['length']
                chain = response.json()['chain']

                #Check if the length is longer and the chain is valid
                if (length > maxLength and self.validChain(chain)):
                    maxLength = length
                    newChain = chain
        
        #Replace our chain if we find a valid longer chain than ours
        if newChain:
            self.chain = newChain
            return True
        
        return False



#Instantiate our Node
app = Flask(__name__)

#Generate a globally unique address for this node
nodeIdentifier = str(uuid4()).replace('-', '')

#Initiate the Blockchain
blockchain = BlockChain()

@app.route('/')
def index():
    return '<center><h1>Aura Blockchain<h1></center>'

@app.route('/mine', methods=['GET'])
def mine():
    #Run the PoW Algorithm to find the next PoW
    lastBlock = blockchain.lastBlock
    # lastProof = lastBlock['proof']
    proof = blockchain.proofOfWork(lastBlock)

    # We must receive a reward for finding the proof.
    # The sender is "0" to signify that this node has mined a new coin.

    blockchain.newTransaction(
        sender="0",
        receiver=nodeIdentifier,
        amount=1
    )

    #Forge a new coin by adding it to the chain
    previousHash = blockchain.hash(lastBlock)
    block = blockchain.newBlock(proof, previousHash)

    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previousHash': block['previousHash'],
    }
    return jsonify(response), 200

@app.route('/transaction/new', methods=['POST'])
def newTransaction():
    values = request.get_json()
    #Check the required fields are in the POST'ed data
    required = ['sender', 'receiver', 'amount']
    
    if not all(k in values for k in required):
        return 'Missing Values', 400

    #Create new transaction
    index = blockchain.newTransaction(values['sender'], values['receiver'], values['amount'])

    response = {'message': f'Transaction will be added to the Block{index}'}

    return jsonify(response), 201

@app.route('/nodes/register', methods=['POST'])
def registerNodes():
    values = request.get_json()
    nodes = values.get('nodes')

    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.registerNode(node)

    response = {
        'message': 'New nodes have been added',
        'totalNodes': list(blockchain.nodes),
    }

    return jsonify(response), 200

@app.route('/nodes/show', methods=['GET'])
def showNodes():
    response = {
        'message': 'These are the current nodes:',
        'totalNodes': list(blockchain.nodes),
    }

    return jsonify(response), 200


@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolveConflicts()
    
    if replaced:
        response = {
            'message': 'Our Chain was replaced',
            'new chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is the Authoritative',
            'chain': blockchain.chain
        }
  
    return jsonify(response), 200

@app.route('/chain', methods=['GET'])
def fullChain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200

if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='port to listen on')
    args = parser.parse_args()
    port = args.port

    app.run(host='0.0.0.0', port=port)