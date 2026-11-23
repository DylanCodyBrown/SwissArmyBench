namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>What a result is inserted as: a SQL cell's text and a Python cell's.</summary>
public sealed record InsertText(string Sql = "", string Python = "");
