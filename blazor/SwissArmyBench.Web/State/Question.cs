namespace SwissArmyBench.Web.State;

/// <summary>A question on the app's own dialog (never the browser's confirm() or prompt()).</summary>
/// <param name="Title">The dialog's heading.</param>
/// <param name="Words">One sentence under it.</param>
/// <param name="Yes">The button that agrees ("Delete", "Create").</param>
/// <param name="Asks">A text box's label, when the question asks for words (null: a yes or no).</param>
/// <param name="Value">The text box's first value.</param>
/// <param name="Danger">The yes button in the error colour (a delete).</param>
public sealed record Question(
    string Title,
    string Words,
    string Yes,
    string? Asks = null,
    string Value = "",
    bool Danger = false);
