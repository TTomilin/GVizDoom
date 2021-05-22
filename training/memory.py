from numpy import ndarray
from typing import Tuple, List

import os
import pickle
import random  # Handling random number generation
import itertools
import numpy as np
from collections import deque


class ExperienceReplay:
    PER_e = 0.01  # Avoid some experiences to have 0 probability of being taken
    PER_a = 0.6   # Make a trade-off between random sampling and only taking high priority exp
    PER_b = 0.4   # Importance-sampling, from initial value increasing to 1
    PER_b_increment = 0.001  # Importance-sampling increment per sampling

    absolute_error_upper = 1.  # clipped abs error

    def __init__(self, experience_path: str, save = False, prioritized = False, capacity = 10000,
                 storage_size = 5000, n_last_samples_included = 3):
        """
        Experience replay buffer based on the collections.deque
        ;param experience_path: Path in which to load the experience from and store it in
        :param save: Flag to control the saving of the replay buffer
        :param prioritized: Flag to select prioritized experience replay instead of epsilon-greedy
        :param capacity: The size of the buffer, i.e. the number of last transitions to save
        :param storage_size: How many transitions are saved to the disk
        :param n_last_samples_included: Number of most recent observations included into the sample batch
        """
        self.capacity = capacity
        self.storage_size = storage_size
        self.include_last = n_last_samples_included
        self.experience_path = experience_path
        self.prioritized = prioritized
        self.save_experience = save
        self.buffer = SumTree(capacity) if prioritized else deque(maxlen = capacity)

    def add(self, experiences: ndarray) -> None:
        """
        Store the transitions of the designated previous n steps in a replay buffer
        Pop the leftmost transitions as the oldest in case the experience replay capacity is breached
        In case of prioritized replay find the max priority of the SumTree and add the experiences
        to the tree buffer with that priority value
        :param experiences: Numpy array of transitions (<s, a, r, s', t>) of multi_step size
        :return: None
        """
        if not self.prioritized:
            # self.buffer.appendleft(experience)
            # if self.buffer_size > self.capacity:
            #     self.buffer.pop()
            self.buffer.append(experiences)
            if self.buffer_size > self.capacity:
                self.buffer.popleft()
            return

        # Find the maximum priority of the tree
        max_priority = np.max(self.buffer.tree[-self.buffer.capacity:])

        # Use minimum priority if the priority is 0, otherwise this experience will never have a chance to be selected
        if max_priority == 0:
            max_priority = self.absolute_error_upper

        # Add the new experience to the tree with the maximum priority
        self.buffer.add(max_priority, experiences)

    def sample(self, batch_size: int, trace_length = 1) -> Tuple[ndarray, ndarray, ndarray]:
        """
        Sample a batch of transitions from replay buffer
        :param batch_size: size of the sampled batch
        :param trace_length: length of the experience trace
        :return: tuple of numpy arrays with batch_size as the first dimension
        """
        if not self.prioritized:
            if trace_length > 1:
                points = random.sample(range(0, self.buffer_size - trace_length), batch_size)
                batch = [list(itertools.islice(self.buffer, point, point + trace_length)) for point in points]
                # for trace in batch:
                #     trace.reverse()
                batch = np.array(batch)
            else:
                batch = random.sample(self.buffer, batch_size)
                # Include a specified number of samples from the end of the buffer for better data usage
                for i in range(self.include_last):
                    index = -(i + 1)
                    batch[index] = self.buffer[index]
            return None, np.array(batch), None

        # Create a sample array that will contain the mini-batch
        memory_b = []

        # Create placeholders for the tree indexes and importance sampling weights
        b_idx = np.empty((batch_size,), dtype = np.int32)
        b_ISWeights = np.empty((batch_size, 1), dtype = np.float32)

        # Calculate the priority segment

        # Divide the Range[0, p_total] into n ranges
        priority_segment = self.buffer.total_priority / batch_size  # Priority segment

        # Increase the PER_b each time a new mini-batch is sampled
        self.PER_b = np.min([1., self.PER_b + self.PER_b_increment])  # Max = 1

        # Calculate the max_weight. Set it to a small value to avoid division by zero
        p_min = np.min(self.buffer.tree[-self.buffer.capacity:]) / self.buffer.total_priority
        max_weight = 1e-7 if p_min == 0 else (p_min * batch_size) ** (-self.PER_b)

        for i in range(batch_size):
            """
            Uniformly sample a value from each range
            """
            a, b = priority_segment * i, priority_segment * (i + 1)
            value = np.random.uniform(a, b)

            """
            Experience that corresponds to each value that is retrieved
            """
            index, priority, data = self.buffer.get_leaf(value)

            # P(j)
            sampling_probabilities = priority / self.buffer.total_priority

            #  IS = (1/N * 1/P(i))**b /max wi == (N*P(i))**-b  /max wi
            b_ISWeights[i, 0] = np.power(batch_size * sampling_probabilities, -self.PER_b) / max_weight

            b_idx[i] = index

            memory_b.append(data)

        return b_idx, np.array(memory_b), b_ISWeights

    def batch_update(self, tree_idx: np.ndarray, abs_errors: np.ndarray) -> None:
        """
        Update the priorities in the tree
        """
        abs_errors += self.PER_e  # convert to abs and avoid 0
        clipped_errors = np.minimum(abs_errors, self.absolute_error_upper)
        ps = np.power(clipped_errors, self.PER_a)

        for ti, p in zip(tree_idx, ps):
            self.buffer.update(ti, p)

    def load(self) -> None:
        """
        Load the experiences from external storage into local memory
        :return: None
        """
        print("Loading experiences into replay memory...")
        self.buffer = pickle.load(open(self.experience_path, 'rb'))
        if not self.prioritized:
            self.buffer = deque(self.buffer)

    def save(self) -> None:
        """
        Save the [storage_size] experiences the into external storage
        to be able to continue training when restarting the program
        :return: None
        """
        if not self.save_experience:
            return
        print("Saving experiences from replay memory...")
        if os.path.exists(self.experience_path):
            os.remove(self.experience_path)
        if self.prioritized:
            stored_experience = self.buffer  # TODO don't store the full tree
        else:
            stored_experience = list(
                itertools.islice(self.buffer, self.buffer_size - self.storage_size, self.buffer_size))
        pickle.dump(stored_experience, open(self.experience_path, 'wb'))

    @property
    def buffer_size(self):
        """
        Retrieve the number of gathered experience
        :return: Current size of the buffer
        """
        return self.buffer.data_pointer if type(self.buffer) == SumTree else len(self.buffer)


class SumTree(object):
    """
    This SumTree is a modified version of the implementation by Morvan Zhou:
    https://github.com/MorvanZhou/Reinforcement-learning-with-tensorflow/blob/master/contents/5.2_Prioritized_Replay_DQN/RL_brain.py
    """
    data_pointer = 0

    """
    Initialize the nodes and data of the tree with zeros
    """
    def __init__(self, capacity):
        self.capacity = capacity  # Number of leaf nodes (final nodes) that contains experiences

        # Generate the tree with all nodes values = 0
        # To understand this calculation (2 * capacity - 1) look at the schema above
        # Remember we are in a binary node (each node has max 2 children) so 2x size of leaf (capacity) - 1 (root node)
        # Parent nodes = capacity - 1
        # Leaf nodes = capacity
        self.tree = np.zeros(2 * capacity - 1)

        """ tree:
            0
           / \
          0   0
         / \ / \
        0  0 0  0  [Size: capacity] it's at this line that there is the priorities score (aka pi)
        """

        # Contains [capacity] experiences
        self.data = np.zeros(capacity, dtype = object)

    """
    Here we add our priority score in the sumtree leaf and add the experience in data
    """

    def add(self, priority, data):
        # Determine the index where the experience will be stored
        tree_index = self.data_pointer + self.capacity - 1

        """ tree:
            0
           / \
          0   0
         / \ / \
        tree_index  0 0  0  We fill the leaves from left to right
        """

        # Update the data frame
        self.data[self.data_pointer] = data

        # Update the leaf
        self.update(tree_index, priority)

        # Increment the data_pointer
        self.data_pointer += 1

        # Return to first index and start overwriting, if the capacity is breached
        if self.data_pointer >= self.capacity:
            self.data_pointer = 0

    """
    Update the leaf priority score and propagate the change through tree
    """
    def update(self, tree_index: int, priority: float) -> None:
        # Change = new priority score - former priority score
        change = priority - self.tree[tree_index]
        self.tree[tree_index] = priority

        # Propagate the change through tree
        while tree_index != 0:  # This is faster than recursively looping

            """
            Here we want to access the line above
            THE NUMBERS IN THIS TREE ARE THE INDEXES NOT THE PRIORITY VALUES

                0
               / \
              1   2
             / \ / \
            3  4 5  [6] 

            If we are in leaf at index 6, we updated the priority score
            We need then to update index 2 node
            So tree_index = (tree_index - 1) // 2
            tree_index = (6-1)//2
            tree_index = 2 (because // round the result)
            """
            tree_index = (tree_index - 1) // 2
            self.tree[tree_index] += change

    """
    Here we get the leaf_index, priority value of that leaf and experience associated with that index
    """

    def get_leaf(self, v):
        """
        Tree structure and array storage:
        Tree index:
             0         -> storing priority sum
            / \
          1     2
         / \   / \
        3   4 5   6    -> storing priority for experiences
        Array type for storing:
        [0,1,2,3,4,5,6]
        """
        parent_index = 0

        while True:  # the while loop is faster than the method in the reference code
            left_child_index = 2 * parent_index + 1
            right_child_index = left_child_index + 1

            # If we reach bottom, end the search
            if left_child_index >= len(self.tree):
                leaf_index = parent_index
                break

            else:  # downward search, always search for a higher priority node

                if v <= self.tree[left_child_index]:
                    parent_index = left_child_index

                else:
                    v -= self.tree[left_child_index]
                    parent_index = right_child_index

        data_index = leaf_index - self.capacity + 1

        return leaf_index, self.tree[leaf_index], self.data[data_index]

    @property
    def total_priority(self):
        return self.tree[0]  # Returns the root node
