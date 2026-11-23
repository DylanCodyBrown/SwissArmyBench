namespace SwissArmyBench.Web.Api;

/// <summary>One fix the server offers with a refusal: a button's words and what it does.</summary>
/// <param name="Label">The button's words ("Install now", "Try again").</param>
/// <param name="Action">install, set_variable, sign_in, open_settings or try_again (domain/refusals.py ACTIONS).</param>
/// <param name="Command">install: the command that installs the missing packages.</param>
/// <param name="Name">set_variable: the variable's name.</param>
/// <param name="Connection">sign_in and open_settings: the connection's name.</param>
public sealed record Fix(string Label, string Action, string? Command = null, string? Name = null, string? Connection = null);
