from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import
from builtins import *
from future import standard_library
standard_library.install_aliases()
import logging
import tempfile
import unittest

from chainer import testing
import numpy as np

from chainerrl.agents import nsq
from chainerrl.q_function import FCStateQFunctionWithDiscreteAction
from chainerrl.q_function import FCLSTMStateQFunction
from chainerrl.envs.abc import ABC
from chainerrl.experiments.train_agent_async import train_agent_async
from chainerrl.explorers.epsilon_greedy import ConstantEpsilonGreedy
from chainerrl.optimizers import rmsprop_async


@testing.parameterize(
    *testing.product({
        't_max': [1, 2],
        'use_lstm': [False],
        'episodic': [True, False],
    }),
    *testing.product({
        't_max': [5],
        'use_lstm': [True, False],
        'episodic': [True, False],
    }),
)
class TestNSQ(unittest.TestCase):

    def setUp(self):
        self.outdir = tempfile.mkdtemp()
        logging.basicConfig(level=logging.DEBUG)

    @testing.attr.slow
    def test_abc(self):
        self._test_abc()

    def _test_abc(self):

        nproc = 8

        def make_env(process_idx, test):
            return ABC(episodic=self.episodic or test,
                       partially_observable=self.use_lstm)

        sample_env = make_env(0, False)
        action_space = sample_env.action_space
        obs_space = sample_env.observation_space
        ndim_obs = obs_space.low.size
        n_actions = action_space.n

        def random_action_func():
            return np.random.randint(n_actions)

        def make_agent(process_idx):
            n_hidden_channels = 50
            if self.use_lstm:
                q_func = FCLSTMStateQFunction(
                    ndim_obs, n_actions,
                    n_hidden_channels=n_hidden_channels,
                    n_hidden_layers=2)
            else:
                q_func = FCStateQFunctionWithDiscreteAction(
                    ndim_obs, n_actions,
                    n_hidden_channels=n_hidden_channels,
                    n_hidden_layers=2)
            opt = rmsprop_async.RMSpropAsync(lr=1e-3, eps=1e-2, alpha=0.99)
            opt.setup(q_func)
            explorer = ConstantEpsilonGreedy(
                process_idx / 10, random_action_func)
            return nsq.NSQ(process_idx, q_func, opt, t_max=1,
                           gamma=0.99, i_target=100,
                           explorer=explorer)

        agent = train_agent_async(
            outdir=self.outdir, processes=nproc, make_env=make_env,
            make_agent=make_agent, steps=40000,
            max_episode_len=5,
            eval_frequency=500,
            eval_n_runs=5,
            successful_score=1,
        )

        agent.stop_episode()

        # Test
        env = make_env(0, True)
        total_r = 0
        obs = env.reset()
        done = False
        r = 0.0

        while not done:
            action = agent.act(obs)
            print(('state:', obs, 'action:', action))
            obs, r, done, _ = env.step(action)
            total_r += r
        self.assertAlmostEqual(total_r, 1)