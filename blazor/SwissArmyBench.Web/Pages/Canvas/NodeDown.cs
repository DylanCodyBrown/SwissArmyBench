using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api.Canvas;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>The pointer went down on a node (its corner's handle: Sizing), with the keys held.</summary>
public sealed record NodeDown(CanvasNode Node, PointerEventArgs Pointer, bool Sizing);
