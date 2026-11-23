namespace SwissArmyBench.Web.Pages.Grids.Cards;

/// <summary>A card the grid page sends to the Analyze board by hand (POST /grids/{id}/cards): a note in Markdown or
/// a Plotly figure as JSON, its title, and its size on the board's twelve columns.</summary>
public sealed record BoardCard(string Kind, string Title, string Body, CardSize Size);
