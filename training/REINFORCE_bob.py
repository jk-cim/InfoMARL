import numpy as np
import itertools
import copy
from collections import namedtuple
from play_episode import play

EpisodeStats = namedtuple('Stats', ['episode_lengths', 'episode_rewards', 'episode_kls'])
Bobservation = namedtuple('Bobservation', ['alice_states', 'alice_actions', 'state',
                                           'value', 'action', 'reward'])

def reinforce(env, alice, bob, num_episodes,
              entropy_scale, value_scale, discount_factor,
              max_episode_length, viz_episode_every = 100):
    """
    REINFORCE (Monte Carlo Policy Gradient) Algorithm for a two-agent system,
    in which the alice is considered part of the env for bob.
    
    Args:
        env: OpenAI environment.
        alice: a trained agent with a predict function 
        bob: an agent to be trained with predict and update functions
        num_episodes: mumber of episodes to run for
        entropy_scale: vector of length num_episodes, or scalar
        value_scale: vector of length num_episodes, or scalar
        discount_factor: time-discount factor
        max_episode_length: maximum number of time steps for an episode
    
    Returns:
        An EpisodeStats object with two numpy arrays for episode_lengths and episode_rewards.
    """
    
    # this allows one to set params to scalars when not wanting to anneal them
    if not isinstance(entropy_scale, (list, np.ndarray)):
        entropy_scale = [entropy_scale]*num_episodes
    if not isinstance(value_scale, (list, np.ndarray)):
        value_scale = [value_scale]*num_episodes

    # Keeps track of useful statistics
    alice_stats = EpisodeStats(episode_lengths = np.zeros(num_episodes),
                               episode_rewards = np.zeros(num_episodes),
                               episode_kls = np.zeros(num_episodes))
    bob_stats = EpisodeStats(episode_lengths = np.zeros(num_episodes),
                             episode_rewards = np.zeros(num_episodes),
                             episode_kls = np.zeros(num_episodes))
    
    # each agent needs own copy of env
    alice_env = env
    bob_env = copy.copy(alice_env)
    
    for i_episode in range(num_episodes):
      
        # occasional viz
        if i_episode % viz_episode_every == 0: play(env, alice, bob, max_episode_length)
      
        # reset envs
        alice_state, goal = alice_env.reset()
        bob_state, _ = bob_env.set_goal(goal)
        
        alice_states = []
        alice_actions = []
        alice_done = False
        
        bob_episode = []
        bob_done = False
        
        # one step in the environment
        for t in itertools.count(start = 1):
          
          # first alice takes a step
          if not alice_done:
            alice_action_probs = alice.predict(alice_state, goal)
            alice_action = np.random.choice(np.arange(len(alice_action_probs)), p = alice_action_probs)
            kl = alice.get_kl(alice_state, goal)
            next_alice_state, alice_reward, alice_done, _ = alice_env.step(alice_action)
            # update alice stats
            alice_stats.episode_rewards[i_episode] += alice_reward
            alice_stats.episode_lengths[i_episode] = t
            alice_stats.episode_kls[i_episode] += kl
          else: # if done, sit still
            alice_action = alice_env.action_to_index['STAY']
            next_alice_state = alice_state
          alice_states.append(alice_state)
          alice_actions.append(alice_action)
          
          # then bob takes a step
          if not bob_done:
            bob_action_probs, bob_value = bob.predict(alice_states, alice_actions, bob_state)
            bob_action = np.random.choice(np.arange(len(bob_action_probs)), p = bob_action_probs)
            z = bob.get_z(alice_states, alice_actions, bob_state)
            next_bob_state, bob_reward, bob_done, _ = bob_env.step(bob_action)
            bob_stats.episode_rewards[i_episode] += bob_reward
            bob_stats.episode_lengths[i_episode] = t
            # keep track of the transition for post-episode training
            bob_episode.append(Bobservation(alice_states = alice_states,
                                            alice_actions = alice_actions,
                                            state = bob_state,
                                            value = bob_value,
                                            action = bob_action,
                                            reward = bob_reward))
          else: # if done, sit still
            bob_next_state = bob_state
          
          # print out which step we're on, useful for debugging.
          print("\rStep {} @ Episode {}/{} ({})".format(
                  t, i_episode + 1, num_episodes, bob_stats.episode_rewards[i_episode - 1]), end="")
          # sys.stdout.flush()

          if (alice_done and bob_done) or t > max_episode_length: break
              
          alice_state = next_alice_state
          bob_state = next_bob_state
    
        # go through the episode and make policy updates
        for t, transition in enumerate(bob_episode):
            # the return after this timestep
            total_return = sum(discount_factor**i * t.reward for i, t in enumerate(bob_episode[t:]))
            # the advantage            
            advantage = total_return - transition.value
            # update bob
            bob.update(transition.alice_states,
                       transition.alice_actions,
                       transition.state,
                       transition.action,
                       advantage,
                       entropy_scale[i_episode],
                       value_scale[i_episode])
    
    return alice_stats, bob_stats