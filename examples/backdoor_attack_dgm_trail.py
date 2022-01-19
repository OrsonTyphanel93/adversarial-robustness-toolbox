
import numpy as np
import tensorflow as tf

from art.attacks.poisoning.backdoor_attack_dgm_trail import GANAttackBackdoor
from art.estimators.generation.tensorflow_gan import TensorFlow2GAN
from art.estimators.generation.tensorflow import TensorFlow2Generator
from art.estimators.classification.tensorflow import TensorFlowV2Classifier


#Mnist generator
def make_generator_model(capacity: int, z_dim: int) -> tf.keras.Sequential():
    model = tf.keras.Sequential()

    model.add(tf.keras.layers.Dense(capacity * 7 * 7 * 4, use_bias=False, input_shape=(z_dim,)))
    model.add(tf.keras.layers.BatchNormalization())
    model.add(tf.keras.layers.LeakyReLU())

    model.add(tf.keras.layers.Reshape((7, 7, capacity * 4)))
    assert model.output_shape == (None, 7, 7, capacity * 4)

    model.add(tf.keras.layers.Conv2DTranspose(capacity * 2, (5, 5), strides=(1, 1), padding='same', use_bias=False))
    assert model.output_shape == (None, 7, 7, capacity * 2)
    model.add(tf.keras.layers.BatchNormalization())
    model.add(tf.keras.layers.LeakyReLU())

    model.add(tf.keras.layers.Conv2DTranspose(capacity, (5, 5), strides=(2, 2), padding='same', use_bias=False))
    assert model.output_shape == (None, 14, 14, capacity)
    model.add(tf.keras.layers.BatchNormalization())
    model.add(tf.keras.layers.LeakyReLU())

    # model.add(layers.Conv2DTranspose(1, (5, 5), strides=(2, 2), padding='same', use_bias=False, activation='tanh'))
    model.add(tf.keras.layers.Conv2DTranspose(1, (5, 5), strides=(2, 2), padding='same', use_bias=False))

    model.add(tf.keras.layers.Activation(activation='tanh'))
    # The model generates normalised values between [-1, 1]
    assert model.output_shape == (None, 28, 28, 1)

    return model


def make_discriminator_model(capacity: int) -> tf.keras.Sequential():
    model = tf.keras.Sequential()

    model.add(tf.keras.layers.Conv2D(capacity, (5, 5), strides=(2, 2), padding='same', input_shape=[28, 28, 1]))
    model.add(tf.keras.layers.LeakyReLU())
    model.add(tf.keras.layers.Dropout(0.3))

    model.add(tf.keras.layers.Conv2D(capacity * 2, (5, 5), strides=(2, 2), padding='same'))
    model.add(tf.keras.layers.LeakyReLU())
    model.add(tf.keras.layers.Dropout(0.3))

    model.add(tf.keras.layers.Flatten())
    model.add(tf.keras.layers.Dense(1))

    return model


# Params

lambda_g = 0.0
BUFFER_SIZE = 50000
batch_size = 32
# EPOCHS = 400
EPOCHS = 2
noise_dim = 100
capacity = 64

# Create attacker trigger
z_trigger = np.random.randn(1, 100)

# Load attacker target

x_target = np.load('../../TEMP/data/devil-28x28.npy') # for mnist
x_target_tf = tf.cast(x_target, tf.float32)

# load dataset
(train_images, train_labels), (_, _) = tf.keras.datasets.mnist.load_data()
x_train = np.reshape(train_images, (train_images.shape[0],) + x_target_tf.shape)
train_images = train_images[:1000]

print(train_images.shape, train_labels.shape)




# train_images = (train_images - 127.5) / 127.5 # Normalize the images to [-1, 1]
train_images = train_images * (2.0 / 255) - 1.0

# Use create batches and shuffle the dataset
train_dataset = tf.data.Dataset.from_tensor_slices(train_images).shuffle(BUFFER_SIZE).batch(batch_size)


# Define Generator
def generator_orig_loss_fct(generated_output):
    return tf.compat.v1.losses.sigmoid_cross_entropy(tf.ones_like(generated_output), generated_output)


generator = TensorFlow2Generator(
    encoding_length=noise_dim,
    model=make_generator_model(capacity, noise_dim))


# Define Discriminator
def discriminator_loss_fct(real_output, generated_output):
    """### Discriminator loss

    The discriminator loss function takes two inputs: real images, and generated images. Here is how to calculate the discriminator loss:
    1. Calculate real_loss which is a sigmoid cross entropy loss of the real images and an array of ones (since these are the real images).
    2. Calculate generated_loss which is a sigmoid cross entropy loss of the generated images and an array of zeros (since these are the fake images).
    3. Calculate the total_loss as the sum of real_loss and generated_loss.
    """
    # [1,1,...,1] with real output since it is true and we want our generated examples to look like it
    real_loss = tf.compat.v1.losses.sigmoid_cross_entropy(
        multi_class_labels=tf.ones_like(real_output), logits=real_output)

    # [0,0,...,0] with generated images since they are fake
    generated_loss = tf.compat.v1.losses.sigmoid_cross_entropy(
        multi_class_labels=tf.zeros_like(generated_output), logits=generated_output)

    total_loss = real_loss + generated_loss

    return total_loss


discriminator_classifier = TensorFlowV2Classifier(
    model=make_discriminator_model(capacity),
    nb_classes=2,
    input_shape=(28, 28, 28, 1))

# Build GAN
gan = TensorFlow2GAN(generator=generator,
                     discriminator=discriminator_classifier,
                     generator_loss=generator_orig_loss_fct,
                     generator_optimizer_fct=tf.compat.v1.train.AdamOptimizer(1e-4),
                     discriminator_loss=discriminator_loss_fct,
                     discriminator_optimizer_fct=tf.compat.v1.train.AdamOptimizer(1e-4))

# Create BackDoorAttack Class
gan_attack = GANAttackBackdoor(gan=gan,
                               z_trigger=z_trigger,
                               x_target=x_target,
                               dataset=train_dataset)

poisoned_generator = gan_attack.poison_estimator(batch_size,
                                       EPOCHS,
                                       lambda_g,
                                       iter_counter=0,
                                       z_min=1000.0)
# poisoned_generator.save('./TEMP/models/cifar10/cifar10-moa-2trial-{}'.format(runs))
# generator_copy.save('./TEMP/models/cifar10/cifar10-moa-{}-{}-{}'.format(LAMBDA, trgr, runs))
