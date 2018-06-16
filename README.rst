Rerun Me
========

A library for rerunning functions in the case of raised exceptions and specific return values with configurable delays.

.. code-block:: python

    @rerunme(on_delay=fibonacci(1000, 3),
             on_error=[ConnectionTimeoutError, DeadlockVictimError],
             on_return=[None]
             on_retry=lambda d, r: log.info('Retrying connection again (#%s) in %s seconds' % (r, d)))
    def connection(conn_str, params):
        conn = db(conn_str, params)
        return db.open()

Installation
------------

The latest version of rerunme is available via ``pip``:

.. code-block:: python

    pip install rerunme

Alternatively, you can download and install from source:

.. code-block:: python

    python setup.py install

Getting Started
---------------

The ``rerunme`` function contains the following signature:

.. code-block:: python

    def rerunme(on_delay=None, on_error=None, on_return=None, on_retry=None, retry_after_delay=False):
        ...

It serves as both a function decorator, and a runnable wrapper and is configurable through it's dynamic parameters. Most
of which are function callbacks which allow the user to highly configure the retrying behavior.

This configurable nature is what sets this library apart from others with similar functionality. Many of which allow
basic configuration using defined retry limits and constant delays between requests, which may be OK for the most
simplistic of use cases. But most applications need more complex functionality which can delay with various common
algorithms such as exponential or fibonacci delays. This library provides a subset of the most common delay generators,
but is easily expandable to fit the application-specific needs.

Delay Generators
^^^^^^^^^^^^^^^^

Different ``on_delay`` generators can be used for increasing the delays between successive retries. Note that the values
for the delays are given in milliseconds.

.. code-block:: python

    @rerunme(on_delay=[1000, 2000], on_error=KeyError)
    def func():
        ...

Generators and iterable items can be used to generate delays too.

.. code-block:: python

    def fancy_generator():
        # yield delays
        ...

    @rerunme(on_delay=fancy_generator)
    def func():
        ...

If a single delay is desired, an ``integer`` or ``float`` value can be given, like so.

.. code-block:: python

    @rerunme(on_delay=1000, on_error=KeyError)
    def func():
        ...

A couple of generator functions are provided in the library. These are the typical algorithms used in most systems, and
can serve as a baseline example for more complex delay systems.

- ``constant(delay, limit)``: yields a constant delay at each iteration
- ``linear(start, increment, limit)``: yields a linearly increasing delay at each iteration
- ``exponential(base, multiplier, limit)``: yields an exponentially increasing delay at each iteration
- ``fibonacci(multiplier, limit)``: yields a delay following the fibonacci pattern at each iteration

If the function fails to yield a response that isn't handled before running out of generated items by the ``on_delay``
generator, a ``MaxRetryException`` is thrown.

.. code-block:: python

    @rerunme(on_delay=None, on_error=KeyError)  # No retries
    def func():
        raise KeyError

    # MaxRetryException is raised

Error Handling
^^^^^^^^^^^^^^

The ``on_error`` can be used to determine if a raised exception should be handled and the function retried. A single
exception can be specified to be handled. If an exception is raised that isn't handled, it will bubble up to the outer
scope without retrying the function.

.. code-block:: python

    @rerunme(on_delay=[1000], on_error=TypeError)
    def func():
        raise KeyError

    # KeyError isn't handled, and is thus raised

Multiple errors can be given as a sequence to handle more than one.

.. code-block:: python

    @rerunme(on_delay=[1000], on_error=[ValueError, TimeoutError])
    def func():
        ...

A callable object (such as a function), can be used for more complex handling of errors. These should accept a single
value, the error raised, and return a boolean indicating ``True`` to handle, or ``False`` to not.

.. code-block:: python

    @rerunme(on_delay=[1000], on_error=lambda x: not isinstance(ValueError, TimeoutError))
    def func():
        ...

Return Value Handling
^^^^^^^^^^^^^^^^^^^^^

Like raised exception, return values can also be handled in a similar manner. Return values that are handled cause the
function to be retried, and those that aren't are simply return. A common use case for this is when interacting with
functions that yield a return value that indicates a failed state (like ``-1`` or ``None``), while other values indicate
a successful state (like ``0`` or an ``object``).

.. code-block:: python

    @rerunme(on_delay=[1000], on_return=-1)
    def func()
        return -1

    # Function is retried because -1 is handled

One note to make is that if a sequence is given, any value that is matched in the sequence is handled. If, however, the
return value is a sequence, either a function should be used to check for equality or ``on_return`` should be a sequence
of sequences, like so.

.. code-block:: python

    # WRONG: checks if [-1, -1] is in the sequence [-1, -1]
    @rerunme(on_delay=[1000], on_return=[-1, -1])
    def func():
        return [-1, -1]  # Not handled

    # CORRECT: checks if [-1, -1] is the return value
    @rerunme(on_delay=[1000], on_return=lambda x: x == [-1, -1])
    def func():
        return [-1, -1] # Is handled

    # CORRECT: checks if [-1, -1] is in the sequence [[-1, -1]]
    @rerunme(on_delay=[1000], on_return=[[-1, -1]])
    def func():
        return [-1, -1] # Is handled

Each time a retry takes place the ``on_retry`` callback is called, if given, passing in the current delay and the number
of retries thus far. Logging is a common use-case for this, as shown below.

.. code-block:: python

    def log(delay, retry):
        logging.info('Retrying function again (#%s) in %s seconds' % (delay, retry))

    @rerunme(on_delay=[1000, 2000, 3000], on_return=-1, on_retry=log)
    def func():
        ...

The ``on_retry`` callback is called prior to waiting for the delay in-between successive retries. If calling the
it after the delay, the ``retry_after_delay`` parameter can be specified.

.. code-block:: python

    @rerunme(on_delay=[1000],
             on_return=-1,
             on_retry=lambda d, r: print('Waited %s seconds for retry #%s' % (d, r)))
    def func():
        ...


Advanced Usage
--------------
Instead of using as a decorator, ``rerunme`` can be used as an instead for wrapping an arbitrary number of function
calls. This can be achieved via the ``run`` method.

.. code-block:: python

    def func_a():
        ...

    def func_b():
        ...

    rerunner = rerunme(on_delay=..., on_error=..., on_return=..., on_retry=...)

    # Using same configured rerunme instance
    rerunme.run(func_a, args, kwargs)
    rerunme.run(func_b, args, kwargs)

Besides using the provided ``run`` method, like any decorator functions can be locally wrapped, passed around, and
executed.

.. code-block:: python

    def func():
        ...

    rerunner = rerunme(on_delay=..., on_error=..., on_return=..., on_retry=...)
    rerun_func = rerunner(func)
    rerun_func(args, kwargs)

    # Or as a one-off like so
    rerunme(...)(func)(args, kwargs)

Each of the function parameters that can be passed into ``rerunme``, can actually be configured to accepts different
number of parameters depending on the function. They can each either accept 0 parameters, the parameters that would be
typically passed in, or the wrapped function's args and kwargs in addition to the parameters typically given.

Optionally passing in the args and kwargs allows for building more complex callback functions. Each of the possible
function variations are shown below.

.. code-block:: python

    def on_delay(): ...
    def on_delay(*args, **kwargs): ...

    def on_error(): ...
    def on_error(error): ...
    def on_error(error, *args, **kwargs): ...

    def on_return(): ...
    def on_return(value): ...
    def on_return(value, *args, **kwargs): ...

    def on_retry(): ...
    def on_retry(delay, retries): ...
    def on_retry(delay, retries, *args, **kwargs): ...


Contribution
------------
Contributions or suggestions are welcome! Feel free to `open an issue`_ if a bug or enhancement is desired, or even a
`pull request`_.

.. _open an issue: https://github.com/jaredlgillespie/rerunme/issues
.. _pull request: https://github.com/jaredlgillespie/rerunme/compare

Changelog
---------
All changes and versioning information can be found in the `CHANGELOG`_.

.. _CHANGELOG: CHANGELOG.rst

License
-------
Copyright (c) 2018 Jared Gillespie. See `LICENSE`_ for details.

.. _LICENSE: LICENSE.txt
