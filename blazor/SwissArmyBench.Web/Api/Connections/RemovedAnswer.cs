namespace SwissArmyBench.Web.Api.Connections;

/// <summary>DELETE /blades/{name}: how many of the model's relationships went with it.</summary>
public sealed record RemovedAnswer(int RelationshipsRemoved = 0);
