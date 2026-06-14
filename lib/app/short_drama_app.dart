import 'package:flutter/material.dart';

import '../core/api/tenant_adapter_client.dart';
import '../features/home/home_screen.dart';
import '../flavor/flavor.dart';
import 'app_runtime.dart';
import '../theme/template_theme.dart';

class ShortDramaApp extends StatefulWidget {
  const ShortDramaApp({
    required this.flavor,
    this.client,
    this.endUserRef,
    this.loadRemoteConfig = false,
    super.key,
  });

  final FlavorConfig flavor;
  final TenantAdapterClient? client;
  final String? endUserRef;
  final bool loadRemoteConfig;

  @override
  State<ShortDramaApp> createState() => _ShortDramaAppState();
}

class _ShortDramaAppState extends State<ShortDramaApp> {
  late final AppRuntime runtime;

  @override
  void initState() {
    super.initState();
    runtime = AppRuntime(
      flavor: widget.flavor,
      endUserRef: widget.endUserRef,
      client: widget.client ??
          TenantAdapterClient(
            baseUri: Uri.parse(widget.flavor.brand.apiAdapterBase),
          ),
    );
    if (widget.loadRemoteConfig) {
      runtime.bootstrap();
    }
  }

  @override
  void dispose() {
    runtime.dispose();
    super.dispose();
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
