import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';

import '../core/api/app_models.dart';
import '../core/api/tenant_adapter_client.dart';
import '../features/home/home_screen.dart';
import '../features/player/player_screen.dart';
import '../flavor/flavor.dart';
import '../theme/template_theme.dart';
import 'app_runtime.dart';
import 'demo_adapter_transport.dart';

abstract class AppDeepLinks {
  Future<Uri?> getInitialLink();

  Stream<Uri> get uriLinkStream;
}

class AppLinksDeepLinks implements AppDeepLinks {
  AppLinksDeepLinks({AppLinks? appLinks}) : _appLinks = appLinks ?? AppLinks();

  final AppLinks _appLinks;

  @override
  Future<Uri?> getInitialLink() => _appLinks.getInitialLink();

  @override
  Stream<Uri> get uriLinkStream => _appLinks.uriLinkStream;
}

class ShortDramaApp extends StatefulWidget {
  const ShortDramaApp({
    required this.flavor,
    this.client,
    this.endUserRef,
    this.loadRemoteConfig = false,
    this.deepLinks,
    super.key,
  });

  final FlavorConfig flavor;
  final TenantAdapterClient? client;
  final String? endUserRef;
  final bool loadRemoteConfig;
  final AppDeepLinks? deepLinks;

  @override
  State<ShortDramaApp> createState() => _ShortDramaAppState();
}

class _ShortDramaAppState extends State<ShortDramaApp> {
  late final AppRuntime runtime;
  late final AppDeepLinks deepLinks;
  late final bool usesDemoTransport;
  final navigatorKey = GlobalKey<NavigatorState>();
  final handledShareDeepLinks = <String>{};
  StreamSubscription<Uri>? deepLinkSubscription;

  @override
  void initState() {
    super.initState();
    usesDemoTransport = !widget.loadRemoteConfig && widget.client == null;
    runtime = AppRuntime(
      flavor: widget.flavor,
      endUserRef: widget.endUserRef,
      isDemoMode: usesDemoTransport,
      client: widget.client ??
          TenantAdapterClient(
            baseUri: Uri.parse(widget.flavor.brand.apiAdapterBase),
            transport: usesDemoTransport
                ? DemoAdapterTransport(
                    flavor: widget.flavor,
                    endUserRef: widget.endUserRef,
                  )
                : null,
          ),
    );
    deepLinks = widget.deepLinks ?? AppLinksDeepLinks();
    startDeepLinkListening();
    if (widget.loadRemoteConfig || usesDemoTransport) {
      runtime.bootstrap();
    }
  }

  @override
  void dispose() {
    deepLinkSubscription?.cancel();
    runtime.dispose();
    super.dispose();
  }

  void startDeepLinkListening() {
    deepLinks.getInitialLink().then((uri) {
      if (uri != null) {
        handleDeepLink(uri);
      }
    }).catchError((_) {});
    deepLinkSubscription = deepLinks.uriLinkStream.listen(
      handleDeepLink,
      onError: (_) {},
    );
  }

  void handleDeepLink(Uri uri) {
    final target = parseSharedEpisodeTarget(uri);
    if (target == null) {
      return;
    }
    if (!handledShareDeepLinks.add(target.dedupeKey)) {
      return;
    }
    resolveSharedEpisodeLink(target).then((shareLink) {
      pushSharedEpisode(shareLink);
    }).catchError((_) {
      pushSharedEpisode(fallbackSharedEpisodeLink(target));
    });
  }

  void pushSharedEpisode(SharedEpisodeLink shareLink) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      final navigator = navigatorKey.currentState;
      if (navigator == null) {
        return;
      }
      navigator.push(
        MaterialPageRoute(
          builder: (_) => PlayerScreen(
            flavor: widget.flavor,
            dramaId: shareLink.dramaId,
            episodeId: shareLink.episodeId,
            dramaTitle: shareLink.dramaTitle,
            episodeTitle: shareLink.episodeTitle,
            episodes: shareLink.episodes,
          ),
        ),
      );
    });
  }

  SharedEpisodeTarget? parseSharedEpisodeTarget(Uri uri) {
    if (uri.scheme != widget.flavor.deepLinkScheme) {
      return null;
    }
    final segments = [
      if (uri.host.isNotEmpty) uri.host,
      ...uri.pathSegments,
    ];
    final dramasIndex = segments.indexOf('dramas');
    if (dramasIndex < 0 || dramasIndex + 3 >= segments.length) {
      return null;
    }
    if (segments[dramasIndex + 2] != 'episodes') {
      return null;
    }
    final dramaId = Uri.decodeComponent(segments[dramasIndex + 1]).trim();
    final episodeId = Uri.decodeComponent(segments[dramasIndex + 3]).trim();
    if (dramaId.isEmpty || episodeId.isEmpty) {
      return null;
    }
    return SharedEpisodeTarget(dramaId: dramaId, episodeId: episodeId);
  }

  Future<SharedEpisodeLink> resolveSharedEpisodeLink(
    SharedEpisodeTarget target,
  ) async {
    final localDrama = catalogDramaById(target.dramaId);
    if (localDrama != null) {
      return sharedEpisodeLinkFrom(
        target: target,
        drama: localDrama,
        episodes: fallbackEpisodes(dramaId: target.dramaId, drama: localDrama),
      );
    }
    final detail = await runtime.fetchDrama(target.dramaId);
    return sharedEpisodeLinkFrom(
      target: target,
      drama: detail.drama,
      episodes: detail.episodes.isEmpty
          ? fallbackEpisodes(dramaId: target.dramaId, drama: detail.drama)
          : detail.episodes,
    );
  }

  SharedEpisodeLink fallbackSharedEpisodeLink(SharedEpisodeTarget target) {
    final drama = catalogDramaById(target.dramaId);
    return sharedEpisodeLinkFrom(
      target: target,
      drama: drama,
      episodes: fallbackEpisodes(dramaId: target.dramaId, drama: drama),
    );
  }

  SharedEpisodeLink sharedEpisodeLinkFrom({
    required SharedEpisodeTarget target,
    required CatalogDrama? drama,
    required List<DramaEpisode> episodes,
  }) {
    final resolvedEpisodes = episodes.isEmpty
        ? fallbackEpisodes(dramaId: target.dramaId, drama: drama)
        : episodes;
    final episode = episodeById(resolvedEpisodes, target.episodeId);
    return SharedEpisodeLink(
      dramaId: target.dramaId,
      episodeId: target.episodeId,
      dramaTitle: drama?.title ?? 'Seed Drama',
      episodeTitle: episode?.title ?? target.episodeId,
      episodes: resolvedEpisodes,
    );
  }

  CatalogDrama? catalogDramaById(String dramaId) {
    for (final drama in runtime.catalog) {
      if (drama.dramaId == dramaId) {
        return drama;
      }
    }
    return null;
  }

  DramaEpisode? episodeById(List<DramaEpisode> episodes, String episodeId) {
    for (final episode in episodes) {
      if (episode.episodeId == episodeId) {
        return episode;
      }
    }
    return null;
  }

  List<DramaEpisode> fallbackEpisodes({
    required String dramaId,
    required CatalogDrama? drama,
  }) {
    final episodeCount = drama?.episodeCount ?? 12;
    final safeEpisodeCount = episodeCount < 1 ? 1 : episodeCount;
    return List.generate(
      safeEpisodeCount,
      (index) => DramaEpisode(
        episodeId: index == 0
            ? 'episode_1'
            : '${dramaId}_ep_${(index + 1).toString().padLeft(3, '0')}',
        episodeNumber: index + 1,
        title: 'Episode ${index + 1}',
        pointPrice: drama?.pointPrice ?? 2,
        ready: index < (drama?.readyEpisodeCount ?? 1),
        locked: index > 0,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: runtime,
      builder: (context, _) {
        final tokens = templateTokensFor(
          runtime.effectiveCapabilities.styleTemplate,
          runtime.effectiveBrandPrimaryColor,
        );
        return AppRuntimeScope(
          runtime: runtime,
          child: MaterialApp(
            navigatorKey: navigatorKey,
            debugShowCheckedModeBanner: false,
            title: runtime.appName,
            theme: ThemeData(
              colorScheme: ColorScheme.fromSeed(
                seedColor: tokens.primary,
                brightness: tokens.background.computeLuminance() < 0.25
                    ? Brightness.dark
                    : Brightness.light,
              ),
              useMaterial3: true,
              scaffoldBackgroundColor: tokens.background,
            ),
            home: _runtimeHome(context, tokens),
          ),
        );
      },
    );
  }

  Widget _runtimeHome(BuildContext context, TemplateTokens tokens) {
    if (widget.loadRemoteConfig &&
        runtime.loading &&
        runtime.data.config == null) {
      return Scaffold(
        body: SafeArea(
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                CircularProgressIndicator(color: tokens.primary),
                const SizedBox(height: 16),
                Text(runtime.strings.loadingTenantApp),
              ],
            ),
          ),
        ),
      );
    }
    if (widget.loadRemoteConfig &&
        runtime.error != null &&
        runtime.data.config == null &&
        runtime.catalog.isEmpty) {
      return Scaffold(
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.cloud_off_outlined, size: 56, color: tokens.primary),
                const SizedBox(height: 18),
                Text(
                  runtime.strings.tenantEdgeUnavailable,
                  style: const TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.w900,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                Text('${runtime.error}', textAlign: TextAlign.center),
                const SizedBox(height: 18),
                FilledButton.icon(
                  onPressed: runtime.bootstrap,
                  icon: const Icon(Icons.refresh),
                  label: Text(runtime.strings.retry),
                ),
                TextButton(
                  onPressed: runtime.continueWithFallback,
                  child: Text(runtime.strings.continueWithDemoData),
                ),
              ],
            ),
          ),
        ),
      );
    }
    return HomeScreen(flavor: widget.flavor);
  }
}

class SharedEpisodeTarget {
  const SharedEpisodeTarget({
    required this.dramaId,
    required this.episodeId,
  });

  final String dramaId;
  final String episodeId;

  String get dedupeKey => '$dramaId/$episodeId';
}

class SharedEpisodeLink {
  const SharedEpisodeLink({
    required this.dramaId,
    required this.episodeId,
    required this.dramaTitle,
    required this.episodeTitle,
    required this.episodes,
  });

  final String dramaId;
  final String episodeId;
  final String dramaTitle;
  final String episodeTitle;
  final List<DramaEpisode> episodes;
}
