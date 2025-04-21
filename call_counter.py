def call_counter(n):
  """
  A function decorator that tallies the number of calls to the function it decorates
  and prints the number to the screen every n times.

  Args:
    n: The number of times the function must be called before printing the call count.

  Returns:
    A function decorator.
  """
  def decorator(func):
    """
    The decorator function that keeps track of the call count.

    Args:
      func: The function to be decorated.

    Returns:
      The decorated function.
    """
    call_count = 0
    def wrapper(*args, **kwargs):
      """
      The wrapper function that calls the decorated function and increments the call count.

      Args:
        *args: Arguments passed to the decorated function.
        **kwargs: Keyword arguments passed to the decorated function.

      Returns:
        The result of calling the decorated function.
      """
      nonlocal call_count
      call_count += 1
      if call_count % n == 0:
        print(f"Function '{func.__name__}' called {call_count} times.")
      return func(*args, **kwargs)
    return wrapper
  return decorator
