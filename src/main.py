import numpy as np
import torch
from matplotlib import pyplot

from util import tweet_as_tokens, Embedding, Tweets, load_embedding, load_tweets, split_data


def train(model, x_train, y_train, x_test, y_test, loss_func, optimizer, epochs: int, batch_size: int, device: str):
    losses = np.zeros(epochs // 10)
    train_accs = np.zeros(epochs // 10)
    test_accs = np.zeros(epochs // 10)

    for epoch in range(epochs):
        model.train()

        shuffle = torch.randperm(len(x_train), device=device)
        batch_count = len(x_train) // batch_size

        epoch_loss = 0
        epoch_acc = 0

        for b in range(batch_count):
            batch_i = shuffle[b * batch_size: (b + 1) * batch_size]
            x_train_batch = x_train[batch_i]
            y_train_batch = y_train[batch_i]

            predictions = model.forward(x_train_batch)
            loss = loss_func(predictions, y_train_batch)

            epoch_loss += loss.item() / batch_count
            epoch_acc += accuracy(predictions, y_train_batch) / batch_count

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        y_test_pred = model.forward(x_test)
        test_acc = accuracy(y_test_pred, y_test)
        print(f'Epoch {epoch}/{epochs}, loss {epoch_loss:.4f} acc {epoch_acc:.4f} test_acc {test_acc:.4f}')

        losses[epoch // 10] = epoch_loss
        train_accs[epoch // 10] = epoch_acc
        test_accs[epoch // 10] = test_acc

    return losses, train_accs, test_accs


# TODO make including the variance optional
def construct_mean_tensors(emb: Embedding, tweets: Tweets, tweet_count: int):
    assert tweet_count <= len(tweets.pos) and tweet_count <= len(tweets.neg), "Too many tweets"

    x = torch.empty(2 * tweet_count, 2 * emb.size)
    y = torch.empty(2 * tweet_count, dtype=torch.long)
    next_i = 0

    for pos, curr_tweets in [(1, tweets.pos), (0, tweets.neg)]:
        for tweet in curr_tweets[:tweet_count]:
            tokens = tweet_as_tokens(tweet, emb.word_dict)
            if len(tokens) == 0 or len(tokens) == 1:
                continue

            x[next_i, :emb.size], x[next_i, emb.size:] = torch.var_mean(torch.tensor(emb.ws[tokens, :]), dim=0)
            y[next_i] = pos

            next_i = next_i + 1

    # remove excess capacity
    print(f"Dropped {len(x) - next_i} empty tweets")
    x = x[:next_i]
    y = y[:next_i]

    return x, y


def construct_sequential_tensors(emb: Embedding, tweets: Tweets, tweet_count: int, max_length: int):
    assert tweet_count <= len(tweets.pos) and tweet_count <= len(tweets.neg), "Too many tweets"

    # todo maybe store index in x instead of expanded embedding
    x = torch.zeros(2 * tweet_count, max_length, emb.size)
    y = torch.empty(2 * tweet_count, dtype=torch.long)
    cropped_count = 0

    tweet_i = 0

    for pos, curr_tweets in [(1, tweets.pos), (0, tweets.neg)]:
        for tweet in curr_tweets[:tweet_count]:
            tokens = tweet_as_tokens(tweet, emb.word_dict)
            if len(tokens) > max_length:
                cropped_count += 1

            for token_i, token in enumerate(tokens):
                if token_i >= max_length:
                    break

                x[tweet_i, token_i, :] = torch.tensor(emb.ws[token, :])

            y[tweet_i] = pos
            tweet_i = tweet_i + 1

    return x, y


def accuracy(y_pred, y) -> float:
    y_pred = torch.argmax(y_pred, dim=1)
    return torch.eq(y_pred, y).float().mean()


def plot_tweet_lengths(tweets: Tweets, max_length: int):
    pos_lengths = list(tweet.count(" ") for tweet in tweets.pos)
    neg_lengths = list(tweet.count(" ") for tweet in tweets.neg)

    pyplot.hist([pos_lengths, neg_lengths], range=(0, max_length), bins=max_length, label=["pos", "neg"], density=True)
    pyplot.legend()
    pyplot.xlabel("word count")
    pyplot.ylabel("frequency")
    pyplot.show()

    dropped_count = sum(1 for length in pos_lengths + neg_lengths if length > max_length)
    total_count = len(pos_lengths) + len(neg_lengths)
    print(f"max_length={max_length} drops {dropped_count} ({dropped_count / total_count:.4f}) tweets")


def main():
    emb = load_embedding("size_200")
    tweets = load_tweets()

    epochs = 200
    learning_rate = 1e-2
    train_ratio = .95

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device {device}")

    print("Constructing tensors")
    x, y = construct_mean_tensors(emb=emb, tweets=tweets, tweet_count=200_000)
    x = x.to(device)
    y = y.to(device)

    x_train, y_train, x_test, y_test = split_data(x, y, train_ratio)

    model = torch.nn.Sequential(
        torch.nn.Linear(x.shape[1], 50),
        torch.nn.ReLU(),
        torch.nn.Dropout(),
        torch.nn.Linear(50, 2),
    )
    model.to(device)

    cost_func = torch.nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)

    print("Training")
    losses, train_accs, test_accs = train(
        model,
        x_train, y_train, x_test, y_test,
        cost_func, optimizer, epochs, batch_size=1000,
        device=device
    )

    pyplot.plot(losses, label="loss")
    pyplot.plot(train_accs, label="train acc")
    pyplot.plot(test_accs, label="test acc")
    pyplot.legend()
    pyplot.show()


if __name__ == '__main__':
    main()
