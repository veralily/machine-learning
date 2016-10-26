# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Example / benchmark for building a PTB LSTM model.
Trains the model described in:
(Zaremba, et. al.) Recurrent Neural Network Regularization
http://arxiv.org/abs/1409.2329
There are 3 supported model configurations:
===========================================
| config | epochs | train | valid  | test
===========================================
| small  | 13     | 37.99 | 121.39 | 115.91
| medium | 39     | 48.45 |  86.16 |  82.07
| large  | 55     | 37.87 |  82.62 |  78.29
The exact results may vary depending on the random initialization.
The hyperparameters used in the model:
- init_scale - the initial scale of the weights
- learning_rate - the initial value of the learning rate
- max_grad_norm - the maximum permissible norm of the gradient
- num_layers - the number of LSTM layers
- num_steps - the number of unrolled steps of LSTM
- hidden_size - the number of LSTM units
- max_epoch - the number of epochs trained with the initial learning rate
- max_max_epoch - the total number of epochs for training
- keep_prob - the probability of keeping weights in the dropout layer
- lr_decay - the decay of the learning rate for each epoch after "max_epoch"
- batch_size - the batch size
The data required for this example is in the data/ dir of the
PTB dataset from Tomas Mikolov's webpage:
$ wget http://www.fit.vutbr.cz/~imikolov/rnnlm/simple-examples.tgz
$ tar xvf simple-examples.tgz
To run:
$ python ptb_word_lm.py --data_path=simple-examples/data/
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import time

import numpy as np
import tensorflow as tf
import read_data

flags = tf.flags
logging = tf.logging

flags.DEFINE_string(
    "model", "small",
    "A type of model. Possible options are: small, medium, large.")
flags.DEFINE_string(
    "VECTOR_SIZE", 41,
    "A type of model. Possible options are: small, medium, large.")

FLAGS = flags.FLAGS


class PTBModel(object):
  """The PTB model."""

  def __init__(self, is_training, config):
    self.batch_size = batch_size = config.batch_size
    self.num_steps = num_steps = config.num_steps
    size = config.hidden_size
    vocab_size = config.vocab_size

    self._input_data = tf.placeholder(tf.float32, [batch_size, num_steps,FLAGS.VECTOR_SIZE])
    self._targets = tf.placeholder(tf.int32, [batch_size, num_steps])

    # Slightly better results can be obtained with forget gate biases
    # initialized to 1 but the hyperparameters of the model would need to be
    # different than reported in the paper.
    with tf.name_scope("cell_sltm") as scope:
      lstm_cell = tf.nn.rnn_cell.BasicLSTMCell(size, forget_bias=0.0)
      if is_training and config.keep_prob < 1:
        lstm_cell = tf.nn.rnn_cell.DropoutWrapper(
            lstm_cell, output_keep_prob=config.keep_prob)
      cell = tf.nn.rnn_cell.MultiRNNCell([lstm_cell] * config.num_layers)

      self._initial_state = cell.zero_state(batch_size, tf.float32)

      inputs = self._input_data
      outy = self._targets

      if is_training and config.keep_prob < 1:
        inputs = tf.nn.dropout(inputs, config.keep_prob)

    # Simplified version of tensorflow.models.rnn.rnn.py's rnn().
    # This builds an unrolled LSTM for tutorial purposes only.
    # In general, use the rnn() or state_saving_rnn() from rnn.py.
    #
    # The alternative version of the code below is:
    #
    # from tensorflow.models.rnn import rnn
    # inputs = [tf.squeeze(input_, [1])
    #           for input_ in tf.split(1, num_steps, inputs)]
    # outputs, state = rnn.rnn(cell, inputs, initial_state=self._initial_state)
      outputs = []
      state = self._initial_state
      with tf.variable_scope("RNN"):
        for time_step in range(num_steps):
          if time_step > 0: tf.get_variable_scope().reuse_variables()
          (cell_output, state) = cell(inputs[:, time_step, :], state)
          outputs.append(cell_output)

      output = tf.reshape(tf.concat(1, outputs), [-1, size])
      softmax_w = tf.get_variable("softmax_w", [size, vocab_size])
      softmax_b = tf.get_variable("softmax_b", [vocab_size])
      logits = tf.matmul(output, softmax_w) + softmax_b

    with tf.name_scope("loss") as scope:
      loss = tf.nn.seq2seq.sequence_loss_by_example(
          [logits],
          [tf.reshape(outy, [-1])],
          [tf.ones([batch_size * num_steps])])

    with tf.name_scope("cost") as scope:
      self._cost = cost = tf.reduce_sum(loss) / batch_size
    cost_summary = tf.scalar_summary("cost",cost)

    self.merged = tf.merge_summary([cost_summary])

    self._final_state = state
    self._logits = logits

    if not is_training:
      return

    self._lr = tf.Variable(0.0, trainable=False)
    tvars = tf.trainable_variables()
    grads, _ = tf.clip_by_global_norm(tf.gradients(cost, tvars),
                                      config.max_grad_norm)
    optimizer = tf.train.GradientDescentOptimizer(self.lr)
    self._train_op = optimizer.apply_gradients(zip(grads, tvars))

  def assign_lr(self, session, lr_value):
    session.run(tf.assign(self.lr, lr_value))


  @property
  def input_data(self):
    return self._input_data

  @property
  def targets(self):
    return self._targets

  @property
  def initial_state(self):
    return self._initial_state

  @property
  def cost(self):
    return self._cost

  @property
  def final_state(self):
    return self._final_state

  @property
  def lr(self):
    return self._lr

  @property
  def train_op(self):
    return self._train_op

  @property
  def out_logits(self):
    return self._logits

  def merged(self):
    return self.merged


class SmallConfig(object):
  """Small config."""
  init_scale = 0.1
  learning_rate = 1.0
  max_grad_norm = 5
  num_layers = 2
  num_steps = 20
  hidden_size = 200
  max_epoch = 4
  max_max_epoch = 13
  keep_prob = 1.0
  lr_decay = 0.5
  batch_size = 20
  vocab_size = 3


class MediumConfig(object):
  """Medium config."""
  init_scale = 0.05
  learning_rate = 1.0
  max_grad_norm = 5
  num_layers = 2
  num_steps = 35
  hidden_size = 650
  max_epoch = 6
  max_max_epoch = 39
  keep_prob = 0.5
  lr_decay = 0.8
  batch_size = 20
  vocab_size = 2


class LargeConfig(object):
  """Large config."""
  init_scale = 0.04
  learning_rate = 1.0
  max_grad_norm = 10
  num_layers = 2
  num_steps = 40
  hidden_size = 1500
  max_epoch = 14
  max_max_epoch = 55
  keep_prob = 0.35
  lr_decay = 1 / 1.15
  batch_size = 20
  vocab_size = 2


class TestConfig(object):
  """Tiny config, for testing."""
  init_scale = 0.1
  learning_rate = 1.0
  max_grad_norm = 1
  num_layers = 1
  num_steps = 2
  hidden_size = 2
  max_epoch = 1
  max_max_epoch = 1
  keep_prob = 1.0
  lr_decay = 0.5
  batch_size = 20
  vocab_size = 2

def run_epoch(session, m, vectors_data, labels_data, eval_op, summary_writer, verbose=False):
  """Runs the model on the given data."""
  epoch_size = ((len(vectors_data) // m.batch_size) - 1) // m.num_steps
  start_time = time.time()
  costs = 0.0
  iters = 0
  state = m.initial_state.eval()
  true_count = 0
  for step, (x, y) in enumerate(read_data.ptb_iterator(vectors_data, labels_data, m.batch_size,
                                                    m.num_steps)):
    cost, state, out_logits, merged1, _ = session.run([m.cost, m.final_state, m.out_logits, m.merged, eval_op],
                                 {m.input_data: x,
                                  m.targets: y,
                                  m.initial_state: state})
    if (m.num_steps != 1):
      summary_writer.add_summary(merged1,step)

    costs += cost
    iters += m.num_steps

    labels = tf.reshape(y, [-1])
    correct = tf.nn.in_top_k(tf.cast(out_logits, tf.float32), tf.cast(labels, tf.int32), 1, name = "correct")
    eval_correct = tf.reduce_sum(tf.cast(correct, tf.int32))
    true_count += session.run(eval_correct)


    if verbose and step % (epoch_size // 10) == 10:
      print("%.3f perplexity: %.3f speed: %.0f wps" %
            (step * 1.0 / epoch_size, np.exp(costs / iters),
             iters * m.batch_size / (time.time() - start_time)))

  with tf.name_scope("perplexity") as scope:
      perplexity = np.exp(costs / iters)

  perplexity_summary = tf.scalar_summary("perplexity",perplexity)

  with tf.name_scope("precision") as scope:
    precision = true_count/(iters*m.batch_size)

    print("precision:")
    print(precision)

  accuracy_summary = tf.scalar_summary("accuracy", precision)

  merged_2 = tf.merge_summary([perplexity_summary,accuracy_summary])
  merged2 = session.run(merged_2)
  summary_writer.add_summary(merged2)

  return perplexity


def get_config():
  if FLAGS.model == "small":
    return SmallConfig()
  elif FLAGS.model == "medium":
    return MediumConfig()
  elif FLAGS.model == "large":
    return LargeConfig()
  elif FLAGS.model == "test":
    return TestConfig()
  else:
    raise ValueError("Invalid model: %s", FLAGS.model)


def main(_):

  filename = "Data11-17.txt"
  vectors_data1,labels_data1 = read_data.read_data(filename)
  filename = "valid18-20.txt"
  vectors_data2,labels_data2 = read_data.read_data(filename)
  filename = "Data21-25.txt"
  vectors_data3,labels_data3 = read_data.read_data(filename)

  vectors_data = np.vstack((vectors_data1,vectors_data2,vectors_data3))
  print(vectors_data.shape)
  labels_data = np.vstack((np.reshape(labels_data1,(len(labels_data1),1)),
    np.reshape(labels_data2,(len(labels_data2),1)),
      np.reshape(labels_data3,(len(labels_data3),1))))
  labels_data = np.reshape(labels_data,-1)
  print(labels_data.shape)

  filename = "Data4-10.txt"
  validation_data,vlabels_data = read_data.read_data(filename)
  filename = "Data26-29.txt"
  test_data,tlabels_data = read_data.read_data(filename)
  test_data = test_data[0:8000,]
  tlabels_data = tlabels_data[0:8000,]

  config = get_config()
  eval_config = get_config()
  eval_config.batch_size = 1
  eval_config.num_steps = 1

  with tf.Graph().as_default(), tf.Session() as session:

    initializer = tf.random_uniform_initializer(-config.init_scale,
                                                config.init_scale)
    with tf.variable_scope("model", reuse=None, initializer=initializer):
      m = PTBModel(is_training=True, config=config)
    with tf.variable_scope("model", reuse=True, initializer=initializer):
      mvalid = PTBModel(is_training=False, config=config)
      mtest = PTBModel(is_training=False, config=eval_config)
    
    
    tf.initialize_all_variables().run()

    summary_writer = tf.train.SummaryWriter("train/lstm3s",session.graph)

    for i in range(config.max_max_epoch):
      lr_decay = config.lr_decay ** max(i - config.max_epoch, 0.0)
      m.assign_lr(session, config.learning_rate * lr_decay)

      print("Epoch: %d Learning rate: %.3f" % (i + 1, session.run(m.lr)))

      train_perplexity = run_epoch(session, m, vectors_data, labels_data, m.train_op,summary_writer, 
                                   verbose=True)
      print("Epoch: %d Train Perplexity: %.3f" % (i + 1, train_perplexity))

      valid_perplexity = run_epoch(session, mvalid, validation_data, vlabels_data, tf.no_op(),summary_writer)
      print("Epoch: %d Valid Perplexity: %.3f" % (i + 1, valid_perplexity))

    test_perplexity = run_epoch(session, mtest, test_data, tlabels_data, tf.no_op(),summary_writer)
    print("Test Perplexity: %.3f" % test_perplexity)


if __name__ == "__main__":
  tf.app.run()