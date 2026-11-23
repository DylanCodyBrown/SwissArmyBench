namespace SwissArmyBench.Web.Layout.Tour;

/// <summary>One card of the tour (the classic tour.ts Stop): what a place is, when you would use it and how to reach
/// it; where the tour takes the user and the control it lights up.</summary>
/// <param name="Icon">The card's icon.</param>
/// <param name="Word">Its heading.</param>
/// <param name="Line">What it is, when you would use it, and how to reach it.</param>
/// <param name="Area">The rail's area the tour goes to.</param>
/// <param name="Grid">orders (the tour's orders table in front) or pair (the two side by side).</param>
/// <param name="Form">A new connection's form of this kind, with the variable typed into its Server box.</param>
/// <param name="Targets">CSS selectors for the control to light up, tried in order; the first visible wins.
/// {orders} is the tour's orders grid.</param>
/// <param name="Code">A line of code, when it is something you type.</param>
/// <param name="Practice">type or menu: a hands-on card's practice box; Next waits for it.</param>
/// <param name="RailOnly">Shown only while the rail shows this area (an extension's or a mode's).</param>
public sealed record TourStop(
    string Icon,
    string Word,
    string Line,
    string? Area = null,
    string? Grid = null,
    string? Form = null,
    IReadOnlyList<string>? Targets = null,
    string? Code = null,
    string? Practice = null,
    string? RailOnly = null);
