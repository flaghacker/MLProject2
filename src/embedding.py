import os
import random
import time
from collections import Counter
from typing import Optional, List

import numpy as np
import scipy
import scipy.sparse

from src.util import load_tweets, tweet_as_tokens


def select_words(tweets, max_word_count: Optional[int], filter_punctuation: bool) -> List[str]:
    """Select the `max_word_count` most common words in the given tweets"""
    # TODO maybe filter out common words and punctuation
    word_counts = Counter()
    for tweet in tweets:
        for word in tweet.split(" "):
            word_counts[word] += 1

    if filter_punctuation:
        filtered_word_counts = dict()
        for word, count in word_counts.items():
            contains_letter = any('a' <= letter <= 'z' for letter in word)
            if contains_letter:
                filtered_word_counts[word] = count
        word_counts = Counter(filtered_word_counts)

    selection = word_counts.most_common(max_word_count) if max_word_count is not None else word_counts.items()
    min_occurrences = min(pair[1] for pair in selection)
    words = list(pair[0] for pair in selection)

    print(f"Kept {len(words)}/{len(word_counts)} words that occur >= {min_occurrences} times")
    words.sort()
    return words


def construct_cooc(tweets: [str], word_dict: dict) -> scipy.sparse.coo_matrix:
    """Build a sparse co-occurrence matrix"""
    # TODO it should be possible to make this function a lot faster, maybe not in python though
    # TODO maybe limit the max distance between words counted as co-occurring, both for semantics and performance
    counter = Counter()

    for tweet in tweets:
        tokens = tweet_as_tokens(tweet, word_dict)
        for t0 in tokens:
            for t1 in tokens:
                counter[(t0, t1)] += 1

    row = np.fromiter((pair[0] for pair in counter), dtype=int, count=len(counter))
    col = np.fromiter((pair[1] for pair in counter), dtype=int, count=len(counter))
    data = np.fromiter((x for x in counter.values()), dtype=int, count=len(counter))
    cooc = scipy.sparse.coo_matrix((data, (row, col)))

    return cooc


def train_embedding(
        cooc: scipy.sparse.coo_matrix, size: int, epochs: int, batch_size: int,
        eta: float, n_max: int = 100, alpha: float = 3 / 4
):
    """Train a GloVe embedding using batched SGD. `size` is the size of the resulting embedding."""
    w_x = np.random.normal(size=(cooc.shape[0], size)) / size
    w_y = np.random.normal(size=(cooc.shape[1], size)) / size

    for epoch in range(epochs):
        total_cost = 0

        for i in range(len(cooc.data) // batch_size):
            ix = cooc.row[i:i + batch_size]
            jy = cooc.col[i:i + batch_size]
            n = cooc.data[i:i + batch_size]

            log_n = np.log(n)
            fn = np.minimum(1.0, (n / n_max) ** alpha)

            x, y = w_x[ix, :], w_y[jy, :]
            log_n_pred = np.sum(x * y, axis=1)
            total_cost += np.sum(fn * (log_n - log_n_pred) ** 2)

            # TODO rewrite this using pytorch so we can try different optimizers
            scale = np.sum(2 * eta * fn * (log_n - log_n_pred)) / batch_size
            w_x[ix, :] += scale * y
            w_y[jy, :] += scale * x

        avg_cost = total_cost / (len(cooc.data) // batch_size * batch_size)
        print(f"epoch {epoch}, cost {avg_cost}")

    # TODO try returning w_x + w_y here like in the paper instead
    return w_x


def main():
    MAX_WORD_COUNT = 10_000
    MAX_TWEET_COUNT = 500_000

    os.makedirs("../data/output", exist_ok=True)

    print("Reading tweets")
    tweets = load_tweets()
    tweets = tweets.pos + tweets.neg
    random.shuffle(tweets)

    print("Selecting words")
    words = select_words(tweets, MAX_WORD_COUNT, filter_punctuation=True)
    word_dict = {word: i for i, word in enumerate(words)}
    with open("../data/output/emb_words.txt", mode="w") as f:
        for word in words:
            f.write(word + "\n")

    # TODO maybe save cooc as intermediate result to speed up future training
    print("Constructing cooc matrix")
    start = time.perf_counter()
    cooc = construct_cooc(tweets, word_dict)
    print(f"  took {time.perf_counter() - start}s")

    print("Training embedding")
    start = time.perf_counter()
    w = train_embedding(cooc, size=100, epochs=10, batch_size=3, eta=0.001)
    print(f"  took {time.perf_counter() - start}s")
    np.save("../data/output/emb_w.npy", w)


if __name__ == '__main__':
    main()