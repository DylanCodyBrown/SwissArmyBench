namespace SwissArmyBench.Web.Api.Apis;

/// <summary>An API's references (Delete asks first; Rename says the places that still name it).</summary>
public sealed record ApiReferences(IReadOnlyList<ApiReference> References);
