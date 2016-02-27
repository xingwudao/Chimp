'''
File to initialize training.
Contains settings, network definition for Chainer.
Creates the simulator, replay memory, DQN learner, and passes these to the agent framework for training.
'''

import numpy as np

import chainer
import chainer.functions as F
import chainer.links as L
from chainer import cuda, Function, gradient_check, Variable, optimizers, serializers, utils
from chainer import Link, Chain, ChainList

from memories import ReplayMemoryHDF5

from learners import Learner
from agents import DQNAgent

from simulators.pomdp import MOMDPSimulator
from simulators.pomdp import RockSamplePOMDP

print('Setting training parameters...')

settings = {

    # agent settings
    'batch_size' : 16,
    'print_every' : 500,
    'save_dir' : 'results/nets_rocksample_belief_rmsprop',
    'iterations' : 15000,
    'eval_iterations' : 100,
    'eval_every' : 500,
    'save_every' : 500,
    'initial_exploration' : 500,
    'epsilon_decay' : 0.0001, # subtract from epsilon every step
    'eval_epsilon' : 0, # epsilon used in evaluation, 0 means no random actions
    'epsilon' : 1.0,  # Initial exploratoin rate
    'learn_freq' : 1,

    # simulator settings
    'viz' : False,

    # replay memory settings
    'memory_size' : 10000,  # size of replay memory
    'n_frames' : 1,  # number of frames

    # learner settings
    'learning_rate' : 0.00025, 
    'decay_rate' : 0.99, # decay rate for RMSprop, otherwise not used
    'discount' : 0.95, # discount rate for RL
    'clip_err' : False, # value to clip loss gradients to
    'clip_reward' : 1, # value to clip reward values to
    'target_net_update' : 1000, # update the update-generating target net every fixed number of iterations
    'double_DQN' : False, # use Double DQN (based on Deep Mind paper)
    'optim_name' : 'ADAM', # currently supports "RMSprop", "ADADELTA", "ADAM" and "SGD"'
    'gpu' : False,
    'reward_rescale': False,

    # general
    'seed_general' : 1723,
    'seed_simulator' : 5632,
    'seed_agent' : 9826,
    'seed_memory' : 7563

    }

print(settings)

np.random.seed(settings["seed_general"])

print('Setting up simulator...')
pomdp = RockSamplePOMDP(seed=settings['seed_simulator'])
simulator = MOMDPSimulator(pomdp, robs=False)

settings['model_dims'] = simulator.model_dims

print('Initializing replay memory...')
memory = ReplayMemoryHDF5(settings)

print('Setting up networks...')

class Linear(Chain):

    def __init__(self):
        super(Linear, self).__init__(
            l1=F.Bilinear(simulator.model_dims[0] * settings["n_frames"], settings["n_frames"], 20),
            l2=F.Linear(20, 10),
            bn1=L.BatchNormalization(10),
            l3=F.Linear(10, 10),
            l4=F.Linear(10, 20),
            bn2=L.BatchNormalization(20),
            l5=F.Linear(20, 10),
            l6=F.Linear(10, 5),
            l7=F.Linear(5, simulator.n_actions)
        )

    def __call__(self, s, action_history):
        h = F.relu(self.l1(s/10,action_history/10))
        h = F.relu(self.l2(h))
        h = self.bn1(h)
        h = F.relu(self.l3(h))
        h = F.relu(self.l4(h))
        h = self.bn2(h)
        h = F.relu(self.l5(h))
        h = F.relu(self.l6(h))
        output = self.l7(h)
        return output

net = Linear()

print('Initializing the learner...')
learner = Learner(settings)
learner.load_net(net)

print('Initializing the agent framework...')
agent = DQNAgent(settings)

print('Training...')
agent.train(learner, memory, simulator)

print('Loading the net...')
learner = agent.load(settings['save_dir']+'/learner_final.p')

ind_max = learner.val_rewards.index(max(learner.val_rewards))
ind_net = settings['initial_exploration'] + ind_max * settings['eval_every']
agent.load_net(learner,settings['save_dir']+'/net_%d.p' % int(ind_net))


np.random.seed(settings["seed_general"])

print('Evaluating DQN agent...')
print('(reward, MSE loss, mean Q-value, episodes - NA, time)')
reward, MSE_loss, mean_Q_value, episodes, time, paths, actions, rewards = agent.evaluate(learner, simulator, 50000)
print(reward, MSE_loss, mean_Q_value, episodes, time)

print('Evaluating optimal policy...')
print('(reward, NA, NA, episodes - NA, time)')
reward, MSE_loss, mean_Q_value, episodes, time, paths, actions, rewards = agent.evaluate(learner, simulator, 50000, custom_policy=pomdp.heuristic_policy)
print(reward, MSE_loss, mean_Q_value, episodes, time)
