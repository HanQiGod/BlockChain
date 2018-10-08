#!/usr/bin/python
# -*- coding: UTF-8 -*-

import hashlib
import json
from textwrap import dedent
from time import time
from uuid import uuid4
from urlparse import urlparse

from flask import Flask, jsonify, request
import requests 

class Blockchain(object):
    def __init__(self):
        self.chain = []
        self.current_transactions = []

        self.nodes = set()

        # 创建创世块
        self.new_block(previous_hash=1, proof=100)
        
    def new_block(self, proof, previous_hash=None):
        """
        创建一个新的块，并添加到链中
        :param proof: <int> 证明
        :param previous_hash: (Optional) <str> 前一个块的hash值
        :return: <dict> 新的区块
        """

        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }

        # 重置存储交易信息的list
        self.current_transactions = []

        self.chain.append(block)
        return block
    
    def register_node(self, address):
        """
        添加一个新的节点到节点列表中
        :param address: <str> 节点地址：比如'http://192.168.0.5:5000'
        :return: None
        """

        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def new_transaction(self, sender, recipient, amount):
        """
        添加一笔新的交易到transactions中
        :param sender: <str> 发送者地址
        :param recipient: <str> 接收者地址
        :param amount: <int> 数量
        :return: <int> 包含该交易记录的块的索引
        """

        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })

        return self.last_block['index'] + 1

    def valid_chain(self, chain):
        """
        确定一个给定的区块链是否有效
        :param chain: <list> 区块链
        :return: <bool> True 有效, False 无效
        """

        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            # 检查block的hash值是否正确
            if block['previous_hash'] != self.hash(last_block):
                return False

            # 检查工作量证明是否正确
            if not self.valid_proof(last_block['proof'], block['proof']):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self):
        """
        一致性算法，通过将我们的链替换成网络中最长的链来解决冲突
        :return: <bool> True 我们的链被取代, 否则为False
        """

        neighbours = self.nodes
        new_chain = None

        # 我们只查看比我们链长的节点
        max_length = len(self.chain)

        # Grab and verify the chains from all the nodes in our network
        for node in neighbours:
            response = requests.get('http://'+node+'/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # 检查该节点的链是否比我们节点的链长，以及该链是否有效
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        # 如果找到比我们长且有效的链，则替换我们原来的链
        if new_chain:
            self.chain = new_chain
            return True

        return False 

    @property
    def last_block(self):
        # 返回链中的最后一个块
        return self.chain[-1]
        
    @staticmethod
    def hash(block):
        """
        创建区块的SHA-256哈希值
        :param block: <dict> Block
        :return: <str>
        """

        # We must make sure that the Dictionary is Ordered, or we'll have inconsistent hashes
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()


    def proof_of_work(self, last_proof):
        """
        简单工作量证明(POW)算法:
         - 找到一个数字p'，使得hash(pp')值的开头包含4个0, p是上一个块的proof,  p'是新的proof
        :param last_proof: <int>
        :return: <int>
        """

        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1

        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        """
        验证Proof: hash(last_proof, proof)值开头是否包含4个0?
        :param last_proof: <int> 上一个Proof
        :param proof: <int> 当前Proof
        :return: <bool>
        """

        guess = (str(last_proof)+str(proof)).encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"


# 实例化我们的节点
app = Flask(__name__)

# 为这个节点生成一个全局的唯一地址
node_identifier = str(uuid4()).replace('-', '')

# 实例化区块链
blockchain = Blockchain()

@app.route('/mine', methods=['GET'])
def mine():
    # 运行工作量证明算法，获取下一个proof
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)

    # 由于找到了proof，我们获得一笔奖励
    # 发送者为"0", 表明是该节点挖出来的新币
    blockchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1,
    )

    # 创建新的区块，并添加到链中
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash'],
    }
    return jsonify(response), 200
  
@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()

    # 检查需要的字段是不是都有
    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
        return 'Missing values', 400

    # 创建一个新的交易
    index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'])

    response = {'message': 'Transaction will be added to Block ' + str(index)}
    return jsonify(response), 200

@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()

    nodes = values.get('nodes')
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(blockchain.nodes),
    }
    return jsonify(response), 201


@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }

    return jsonify(response), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)