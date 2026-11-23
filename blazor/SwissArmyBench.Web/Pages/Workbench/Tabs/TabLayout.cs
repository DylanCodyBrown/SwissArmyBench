namespace SwissArmyBench.Web.Pages.Workbench.Tabs;

/// <summary>
/// The tab groups of a Notebooks or Scripts page (the classic workbenchGroups.ts): a tree of splits whose leaves are
/// groups of tabs, the group in focus, and the moves (add, show, close, move to another group, split right or down,
/// reorder). A tab is a document's key. A group left empty goes and a split of one child is that child, so the
/// tree stays as simple as what it shows. No drawing here: the page draws it (GroupsView).
/// </summary>
public sealed class TabLayout
{
    // A sash keeps each side of it between a tenth and nine tenths of the pair's room.
    private const double SmallestShare = 0.1;

    private int _counter;

    public TabLayout()
    {
        Focused = new TabGroup(++_counter);
        Root = Focused;
    }

    public LayoutNode Root { get; private set; }

    public TabGroup Focused { get; private set; }

    /// <summary>The groups in their order on screen (left to right, top to bottom).</summary>
    public IReadOnlyList<TabGroup> Groups => Leaves(Root).ToList();

    /// <summary>Every tab, group by group.</summary>
    public IEnumerable<int> AllTabs => Groups.SelectMany(g => g.Tabs);

    public TabGroup? GroupOf(int tab) => Groups.FirstOrDefault(g => g.Tabs.Contains(tab));

    public bool IsShown(int tab) => Groups.Any(g => g.Active == tab);

    /// <summary>The tab in front of the focused group.</summary>
    public int? Current => Focused.Active;

    public void Focus(TabGroup group) => Focused = group;

    /// <summary>A new tab in the focused group, after the one in front, and shown.</summary>
    public void Add(int tab)
    {
        var at = Focused.Active is { } active ? Focused.Tabs.IndexOf(active) + 1 : Focused.Tabs.Count;
        Focused.Tabs.Insert(at, tab);
        Focused.Active = tab;
    }

    /// <summary>The tab brought to the front of its group, and its group focused.</summary>
    public void Show(int tab)
    {
        if (GroupOf(tab) is { } group)
        {
            group.Active = tab;
            Focused = group;
        }
    }

    /// <summary>The tab taken out; its group shows its neighbour, and an emptied group goes (not the last).</summary>
    public void Remove(int tab)
    {
        if (GroupOf(tab) is not { } group)
        {
            return;
        }
        var at = group.Tabs.IndexOf(tab);
        group.Tabs.RemoveAt(at);
        if (group.Active == tab)
        {
            group.Active = group.Tabs.Count == 0 ? null : group.Tabs[Math.Min(at, group.Tabs.Count - 1)];
        }
        Normalize();
    }

    /// <summary>Whether a tab can move out to a group of its own: its group must keep another tab.</summary>
    public bool CanSplit(int tab) => GroupOf(tab)?.Tabs.Count > 1;

    /// <summary>The tab moved into a new group beside its own (Split right, Split down); false when it is its
    /// group's only tab.</summary>
    public bool Split(int tab, SplitSide side)
    {
        if (GroupOf(tab) is not { } from || from.Tabs.Count < 2)
        {
            return false;
        }
        var made = new TabGroup(++_counter);
        Lift(from, tab);
        made.Tabs.Add(tab);
        made.Active = tab;
        var row = side is SplitSide.Left or SplitSide.Right;
        var before = side is SplitSide.Left or SplitSide.Up;
        if (ParentOf(from) is { } parent && parent.Split.Row == row)
        {
            var size = parent.Split.Sizes[parent.Index];
            var at = parent.Index + (before ? 0 : 1);
            parent.Split.Sizes[parent.Index] = size / 2;
            parent.Split.Children.Insert(at, made);
            parent.Split.Sizes.Insert(at, size / 2);
        }
        else
        {
            var pair = new TabSplit(row);
            pair.Children.AddRange(before ? [made, from] : [from, made]);
            pair.Sizes.AddRange([1, 1]);
            Replace(from, pair);
        }
        Focused = made;
        return true;
    }

    /// <summary>The tab moved into another group (at its end), shown there; the group it left goes if emptied.</summary>
    public void MoveTo(int tab, TabGroup target)
    {
        if (GroupOf(tab) is not { } from || from == target)
        {
            return;
        }
        Lift(from, tab);
        target.Tabs.Add(tab);
        target.Active = tab;
        Focused = target;
        Normalize();
    }

    /// <summary>The tab one place left (-1) or right (1) in its row.</summary>
    public void Reorder(int tab, int by)
    {
        if (GroupOf(tab) is not { } group)
        {
            return;
        }
        var at = group.Tabs.IndexOf(tab);
        var to = at + by;
        if (to >= 0 && to < group.Tabs.Count)
        {
            (group.Tabs[at], group.Tabs[to]) = (group.Tabs[to], group.Tabs[at]);
        }
    }

    /// <summary>The next (1) or previous (-1) group, round the end, as a group to focus.</summary>
    public TabGroup NextGroup(int by)
    {
        var all = Groups;
        var at = all.ToList().IndexOf(Focused);
        return all[((at + by) % all.Count + all.Count) % all.Count];
    }

    /// <summary>The next (1) or previous (-1) tab of the focused group, round the end.</summary>
    public int? NextTab(int by)
    {
        if (Focused.Active is not { } active || Focused.Tabs.Count == 0)
        {
            return null;
        }
        var at = Focused.Tabs.IndexOf(active);
        return Focused.Tabs[((at + by) % Focused.Tabs.Count + Focused.Tabs.Count) % Focused.Tabs.Count];
    }

    /// <summary>A sash moved: the child before it takes this share of the pair's room (kept within limits).</summary>
    public static void Resize(TabSplit split, int index, double fraction)
    {
        var share = Math.Clamp(fraction, SmallestShare, 1 - SmallestShare);
        var pair = split.Sizes[index - 1] + split.Sizes[index];
        split.Sizes[index - 1] = pair * share;
        split.Sizes[index] = pair * (1 - share);
    }

    private void Lift(TabGroup from, int tab)
    {
        var at = from.Tabs.IndexOf(tab);
        from.Tabs.RemoveAt(at);
        if (from.Active == tab)
        {
            from.Active = from.Tabs.Count == 0 ? null : from.Tabs[Math.Min(at, from.Tabs.Count - 1)];
        }
    }

    private void Normalize()
    {
        Root = Simplified(Root) ?? new TabGroup(++_counter);
        if (!Groups.Contains(Focused))
        {
            Focused = Groups[0];
        }
    }

    // An empty group goes (unless it is all there is), a split of one child becomes the child.
    private LayoutNode? Simplified(LayoutNode node)
    {
        if (node is not TabSplit split)
        {
            return node is TabGroup { Tabs.Count: 0 } && node != Root ? null : node;
        }
        var kept = split.Children
            .Select((child, i) => (Child: Simplified(child), Size: split.Sizes[i]))
            .Where(c => c.Child is not null && c.Child is not TabGroup { Tabs.Count: 0 })
            .ToList();
        if (kept.Count == 0)
        {
            return null;
        }
        if (kept.Count == 1)
        {
            return kept[0].Child;
        }
        split.Children.Clear();
        split.Children.AddRange(kept.Select(k => k.Child!));
        split.Sizes.Clear();
        split.Sizes.AddRange(kept.Select(k => k.Size));
        return split;
    }

    private void Replace(LayoutNode old, LayoutNode made)
    {
        if (ParentOf(old) is { } parent)
        {
            parent.Split.Children[parent.Index] = made;
        }
        else
        {
            Root = made;
        }
    }

    private (TabSplit Split, int Index)? ParentOf(LayoutNode target) => ParentOf(target, Root);

    private static (TabSplit Split, int Index)? ParentOf(LayoutNode target, LayoutNode node)
    {
        if (node is not TabSplit split)
        {
            return null;
        }
        var at = split.Children.IndexOf(target);
        return at >= 0 ? (split, at) : split.Children.Select(c => ParentOf(target, c)).FirstOrDefault(p => p is not null);
    }

    private static IEnumerable<TabGroup> Leaves(LayoutNode node) =>
        node is TabSplit split ? split.Children.SelectMany(Leaves) : [(TabGroup)node];
}
