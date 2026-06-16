import 'package:flutter/material.dart';

import '../../app/app_runtime.dart';
import '../../core/api/app_models.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';
import '../../theme/template_visuals.dart';
import '../drama_detail/drama_detail_screen.dart';

enum _CatalogSort { latest, readyFirst, lowestCoins }

class CatalogScreen extends StatefulWidget {
  const CatalogScreen({
    required this.flavor,
    this.catalog = const [],
    this.initialQuery = '',
    super.key,
  });

  final FlavorConfig flavor;
  final List<CatalogDrama> catalog;
  final String initialQuery;

  @override
  State<CatalogScreen> createState() => _CatalogScreenState();
}

class _CatalogScreenState extends State<CatalogScreen> {
  final TextEditingController _searchController = TextEditingController();
  final Set<String> _selectedTags = {};
  final Set<String> _selectedRegions = {};
  final Set<String> _selectedLanguages = {};
  _CatalogSort _sort = _CatalogSort.latest;
  String? _selectedTemplateTab;

  @override
  void initState() {
    super.initState();
    _searchController.text = widget.initialQuery.trim();
  }

  @override
  void didUpdateWidget(covariant CatalogScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.initialQuery != oldWidget.initialQuery) {
      _searchController.text = widget.initialQuery.trim();
    }
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final strings = runtime.strings;
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final dark = tokens.background.computeLuminance() < 0.25;
    final catalogDisplay = runtime.data.config?.catalogDisplay ??
        const CatalogDisplayConfig.empty();
    final items = widget.catalog.isEmpty
        ? const [
            CatalogDrama(
              dramaId: 'drama_1',
              title: 'Seed Drama',
              summary: 'Starter catalog item for template preview.',
              posterUrl: '/assets/posters/1.png',
              episodeCount: 12,
              readyEpisodeCount: 3,
              pointPrice: 2,
              language: 'zh-CN',
              regions: ['SG'],
              tags: ['Hot'],
            ),
          ]
        : widget.catalog;
    final filteredItems = _filteredItems(items, catalogDisplay);
    final tags = _metadataOptions(
      items,
      (item) => _catalogFilterLabels(item, catalogDisplay),
    );
    final regions = _metadataOptions(items, (item) => item.regions);
    final languages = _metadataOptions(
      items,
      (item) => item.language.isEmpty ? const [] : [item.language],
    );
    return ColoredBox(
      color: tokens.background,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  strings.catalog,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        color: dark ? Colors.white : null,
                        fontWeight: FontWeight.w900,
                      ),
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: tokens.primary.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  tokens.name,
                  style: TextStyle(
                    color: dark ? Colors.white : tokens.primary,
                    fontWeight: FontWeight.w900,
                    fontSize: 12,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 36,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemBuilder: (context, index) {
                final tab = templateTabs(tokens)[index];
                final selected = _selectedTemplateTab == null
                    ? index == 0
                    : _selectedTemplateTab == tab;
                return TextButton(
                  style: TextButton.styleFrom(
                    backgroundColor: selected
                        ? tokens.primary
                        : tokens.surface.withValues(alpha: dark ? 0.12 : 1),
                    foregroundColor: selected
                        ? Colors.white
                        : dark
                            ? Colors.white70
                            : const Color(0xFF1F2937),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(999),
                    ),
                  ),
                  onPressed: () => setState(() {
                    _selectedTemplateTab = tab;
                    _applyTemplateTab(tab, tags);
                  }),
                  child: Text(tab),
                );
              },
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemCount: templateTabs(tokens).length,
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _searchController,
            decoration: InputDecoration(
              prefixIcon: const Icon(Icons.search),
              hintText: strings.searchDrama,
              filled: true,
              fillColor: tokens.surface.withValues(alpha: dark ? 0.92 : 1),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(tokens.radius),
                borderSide: BorderSide.none,
              ),
            ),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 12),
          _FilterSection(
            tags: tags,
            regions: regions,
            languages: languages,
            selectedTags: _selectedTags,
            selectedRegions: _selectedRegions,
            selectedLanguages: _selectedLanguages,
            onClear: () {
              setState(() {
                _selectedTemplateTab = null;
                _selectedTags.clear();
                _selectedRegions.clear();
                _selectedLanguages.clear();
                _sort = _CatalogSort.latest;
              });
            },
            onTag: (value, selected) {
              setState(() => _toggle(_selectedTags, value, selected));
            },
            onRegion: (value, selected) {
              setState(() => _toggle(_selectedRegions, value, selected));
            },
            onLanguage: (value, selected) {
              setState(() => _toggle(_selectedLanguages, value, selected));
            },
            tokens: tokens,
          ),
          const SizedBox(height: 12),
          SegmentedButton<_CatalogSort>(
            segments: const [
              ButtonSegment(
                value: _CatalogSort.latest,
                label: Text('Latest'),
              ),
              ButtonSegment(
                value: _CatalogSort.readyFirst,
                label: Text('Ready first'),
              ),
              ButtonSegment(
                value: _CatalogSort.lowestCoins,
                label: Text('Lowest coins'),
              ),
            ],
            selected: {_sort},
            onSelectionChanged: (selection) {
              setState(() => _sort = selection.single);
            },
            showSelectedIcon: false,
            multiSelectionEnabled: false,
            emptySelectionAllowed: false,
          ),
          const SizedBox(height: 12),
          Text(
            '${filteredItems.length} ${filteredItems.length == 1 ? 'drama' : 'dramas'}',
            style: TextStyle(
              color: dark ? Colors.white70 : Colors.black87,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 16),
          if (filteredItems.isEmpty)
            const _CatalogEmptyState()
          else
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                childAspectRatio: 0.68,
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
              ),
              itemCount: filteredItems.length,
              itemBuilder: (context, index) {
                final drama = filteredItems[index];
                final dramaFilterLabels =
                    _catalogFilterLabels(drama, catalogDisplay);
                return InkWell(
                  borderRadius: BorderRadius.circular(tokens.radius),
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => DramaDetailScreen(
                        flavor: widget.flavor,
                        dramaId: drama.dramaId,
                        drama: drama,
                      ),
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: DramaPosterCard(
                          tokens: tokens,
                          title: drama.title,
                          index: index,
                          rank: index < 9 ? index + 1 : null,
                          meta:
                              '${drama.readyEpisodeCount}/${drama.episodeCount} · ${drama.pointPrice} coins',
                          onTap: () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => DramaDetailScreen(
                                flavor: widget.flavor,
                                dramaId: drama.dramaId,
                                drama: drama,
                              ),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        drama.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: dark ? Colors.white : Colors.black,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        [
                          if (dramaFilterLabels.isNotEmpty)
                            dramaFilterLabels.first,
                          if (drama.regions.isNotEmpty) drama.regions.first,
                          if (drama.language.isNotEmpty) drama.language,
                        ].join(' · '),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 11,
                          color: dark ? Colors.white54 : Colors.black45,
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
        ],
      ),
    );
  }

  List<CatalogDrama> _filteredItems(
    List<CatalogDrama> items,
    CatalogDisplayConfig catalogDisplay,
  ) {
    final query = _searchController.text.trim().toLowerCase();
    final filtered = items.where((item) {
      if (query.isNotEmpty && !_matchesQuery(item, query, catalogDisplay)) {
        return false;
      }
      if (_selectedTags.isNotEmpty &&
          !_selectedTags.any(
            (tag) => _catalogFilterLabels(item, catalogDisplay).contains(tag),
          )) {
        return false;
      }
      if (_selectedRegions.isNotEmpty &&
          !_selectedRegions.any((region) => item.regions.contains(region))) {
        return false;
      }
      if (_selectedLanguages.isNotEmpty &&
          !_selectedLanguages.contains(item.language)) {
        return false;
      }
      return true;
    }).toList();
    switch (_sort) {
      case _CatalogSort.latest:
        break;
      case _CatalogSort.readyFirst:
        filtered.sort((a, b) {
          final ready = b.readyEpisodeCount.compareTo(a.readyEpisodeCount);
          return ready == 0 ? a.title.compareTo(b.title) : ready;
        });
        break;
      case _CatalogSort.lowestCoins:
        filtered.sort((a, b) {
          final price = a.pointPrice.compareTo(b.pointPrice);
          return price == 0 ? a.title.compareTo(b.title) : price;
        });
        break;
    }
    return filtered;
  }

  bool _matchesQuery(
    CatalogDrama item,
    String query,
    CatalogDisplayConfig catalogDisplay,
  ) {
    final haystack = [
      item.title,
      item.summary,
      item.language,
      ...item.regions,
      ..._catalogFilterLabels(item, catalogDisplay),
    ].join(' ').toLowerCase();
    return haystack.contains(query);
  }

  List<String> _catalogFilterLabels(
    CatalogDrama item,
    CatalogDisplayConfig display,
  ) {
    final values = <String>{};
    for (final tag in item.tags) {
      final trimmed = tag.trim();
      if (trimmed.isNotEmpty) {
        values.add(trimmed);
      }
    }
    for (final optionIds in item.categorySelections.values) {
      for (final optionId in optionIds) {
        final trimmed = optionId.trim();
        final duplicatesExistingMetadata =
            item.regions.contains(trimmed) || item.language == trimmed;
        if (trimmed.isNotEmpty &&
            !duplicatesExistingMetadata &&
            display.isOptionVisible(trimmed)) {
          values.add(display.labelForOption(trimmed));
        }
      }
    }
    return values.toList(growable: false);
  }

  List<String> _metadataOptions(
    List<CatalogDrama> items,
    Iterable<String> Function(CatalogDrama item) read,
  ) {
    final values = <String>{};
    for (final item in items) {
      for (final value in read(item)) {
        final trimmed = value.trim();
        if (trimmed.isNotEmpty) {
          values.add(trimmed);
        }
      }
    }
    return values.toList()..sort();
  }

  void _toggle(Set<String> target, String value, bool selected) {
    _selectedTemplateTab = null;
    if (selected) {
      target.add(value);
    } else {
      target.remove(value);
    }
  }

  void _applyTemplateTab(String tab, List<String> availableTags) {
    final normalized = tab.trim().toLowerCase();
    _searchController.clear();
    _selectedTags.clear();
    _selectedRegions.clear();
    _selectedLanguages.clear();
    _sort = _CatalogSort.latest;

    final tag = _matchingTag(tab, availableTags);
    if (tag != null) {
      _selectedTags.add(tag);
      return;
    }
    if (normalized.contains('rank') || normalized.contains('theater')) {
      _sort = _CatalogSort.readyFirst;
      return;
    }
    if (normalized.contains('coin')) {
      _sort = _CatalogSort.lowestCoins;
      return;
    }
    _sort = _CatalogSort.latest;
  }

  String? _matchingTag(String tab, List<String> availableTags) {
    final normalized = tab.trim().toLowerCase();
    for (final tag in availableTags) {
      if (tag.trim().toLowerCase() == normalized) {
        return tag;
      }
    }
    return null;
  }
}

class _FilterSection extends StatelessWidget {
  const _FilterSection({
    required this.tags,
    required this.regions,
    required this.languages,
    required this.selectedTags,
    required this.selectedRegions,
    required this.selectedLanguages,
    required this.onClear,
    required this.onTag,
    required this.onRegion,
    required this.onLanguage,
    required this.tokens,
  });

  final List<String> tags;
  final List<String> regions;
  final List<String> languages;
  final Set<String> selectedTags;
  final Set<String> selectedRegions;
  final Set<String> selectedLanguages;
  final VoidCallback onClear;
  final void Function(String value, bool selected) onTag;
  final void Function(String value, bool selected) onRegion;
  final void Function(String value, bool selected) onLanguage;
  final TemplateTokens tokens;

  @override
  Widget build(BuildContext context) {
    final hasFilters = selectedTags.isNotEmpty ||
        selectedRegions.isNotEmpty ||
        selectedLanguages.isNotEmpty;
    final dark = tokens.background.computeLuminance() < 0.25;
    final chipTheme = Theme.of(context).chipTheme;
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        FilterChip(
          label: const Text('All'),
          selected: !hasFilters,
          backgroundColor: tokens.surface.withValues(alpha: dark ? 0.12 : 1),
          selectedColor: tokens.primary.withValues(alpha: 0.18),
          labelStyle: chipTheme.labelStyle?.copyWith(
            color: dark ? Colors.white : null,
            fontWeight: FontWeight.w800,
          ),
          onSelected: (_) => onClear(),
        ),
        for (final tag in tags)
          FilterChip(
            label: Text(tag),
            selected: selectedTags.contains(tag),
            backgroundColor: tokens.surface.withValues(alpha: dark ? 0.12 : 1),
            selectedColor: tokens.primary.withValues(alpha: 0.18),
            labelStyle: chipTheme.labelStyle?.copyWith(
              color: dark ? Colors.white : null,
              fontWeight: FontWeight.w800,
            ),
            onSelected: (selected) => onTag(tag, selected),
          ),
        for (final region in regions)
          FilterChip(
            label: Text(region),
            selected: selectedRegions.contains(region),
            backgroundColor: tokens.surface.withValues(alpha: dark ? 0.12 : 1),
            selectedColor: tokens.primary.withValues(alpha: 0.18),
            labelStyle: chipTheme.labelStyle?.copyWith(
              color: dark ? Colors.white : null,
              fontWeight: FontWeight.w800,
            ),
            onSelected: (selected) => onRegion(region, selected),
          ),
        for (final language in languages)
          FilterChip(
            label: Text(language),
            selected: selectedLanguages.contains(language),
            backgroundColor: tokens.surface.withValues(alpha: dark ? 0.12 : 1),
            selectedColor: tokens.primary.withValues(alpha: 0.18),
            labelStyle: chipTheme.labelStyle?.copyWith(
              color: dark ? Colors.white : null,
              fontWeight: FontWeight.w800,
            ),
            onSelected: (selected) => onLanguage(language, selected),
          ),
      ],
    );
  }
}

class _CatalogEmptyState extends StatelessWidget {
  const _CatalogEmptyState();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 48),
      child: Column(
        children: [
          Icon(Icons.search_off_outlined, size: 42, color: Colors.black45),
          SizedBox(height: 10),
          Text(
            'No dramas match these filters',
            style: TextStyle(fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }
}
